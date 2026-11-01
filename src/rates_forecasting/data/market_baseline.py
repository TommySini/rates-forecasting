"""Read-only market probability reconstruction with explicit contract assumptions."""

from __future__ import annotations

import hashlib
import json
import re

import numpy as np
import pandas as pd

from rates_forecasting.data.cache import SourceUnavailable
from rates_forecasting.data.markets import KALSHI, last_quote

POLY_INVENTORY_QUERY = {
    "tag_id": 100196,
    "closed": "true",
    "end_date_max": "2026-01-01T00:00:00Z",
    "limit": 100,
    "offset": 0,
}
POLY_BUCKETS = {
    "50+ bps decrease": "cut",
    "25 bps decrease": "cut",
    "no change": "hold",
    "25+ bps increase": "hike",
}


def threshold_distribution(lower_threshold_price, current_threshold_price):
    """P(U'>U-step), P(U'>U); valid on the explicitly assumed target grid."""
    a, b = float(lower_threshold_price), float(current_threshold_price)
    if not np.isfinite([a, b]).all() or not (0 <= b <= a <= 1):
        raise ValueError("Invalid or nonmonotone threshold prices")
    return np.array([1 - a, a - b, b])


def simplex_projection(values):
    values = np.asarray(values, dtype=float)
    ordered = np.sort(values)[::-1]
    cumulative = np.cumsum(ordered) - 1
    rho = np.flatnonzero(ordered - cumulative / np.arange(1, len(values) + 1) > 0)[-1]
    return np.maximum(values - cumulative[rho] / (rho + 1), 0)


def partition_distribution(contracts, *, reviewed, max_sum_error, method="proportional"):
    """Reconcile only a reviewed related partition; never unrelated binary bets."""
    if not reviewed or contracts.event_id.nunique() != 1:
        raise ValueError("One reviewed mutually exclusive/exhaustive event required")
    if contracts.contract_id.duplicated().any() or len(contracts) != 4:
        raise ValueError("Duplicate or incomplete partition")
    if set(contracts.bucket) != set(POLY_BUCKETS):
        raise ValueError("Unmapped outcome or incomplete partition")
    if not contracts.target_definition.eq("scheduled_upper_target_change").all():
        raise ValueError("Mixed rate-level and rate-change targets")
    prices = contracts.price.to_numpy(float)
    if not np.isfinite(prices).all() or ((prices < 0) | (prices > 1)).any():
        raise ValueError("Missing or invalid outcome prices")
    total = prices.sum()
    if total <= 0 or abs(total - 1) > max_sum_error:
        raise ValueError("Price sum outside prespecified reconciliation tolerance")
    if method == "proportional":
        coherent = prices / total
    elif method == "simplex":
        coherent = simplex_projection(prices)
    else:
        raise ValueError("Unknown reconciliation method")
    mapped = pd.Series(coherent).groupby(contracts.bucket.map(POLY_BUCKETS).to_numpy()).sum()
    return mapped.reindex(["cut", "hold", "hike"]).to_numpy()


def known_policy(events, cutoff):
    eligible = events[
        (events.label_available_at <= cutoff) & events.target_upper_after.notna()
    ].sort_values("label_available_at")
    if eligible.empty:
        raise ValueError("No policy target available at issuance")
    return eligible.iloc[-1]


def compatible_direction(meeting, policy, intervening_unscheduled_change, *, level_target):
    before_width = meeting.target_upper_before - meeting.target_lower_before
    after_width = meeting.target_upper_after - meeting.target_lower_after
    if not np.isfinite([before_width, after_width]).all() or not np.isclose(
        before_width, after_width
    ):
        raise ValueError("Upper-bound versus midpoint incompatibility: range width changed/unknown")
    if level_target and (
        pd.isna(intervening_unscheduled_change) or bool(intervening_unscheduled_change)
    ):
        raise ValueError("Rate-level target incompatible: intervening change or uncertain history")
    if level_target and not np.isclose(policy.target_upper_after, meeting.target_upper_before):
        raise ValueError("Policy target changed between issuance and scheduled decision")


def _selected(quotes, cutoff, config):
    row, status = last_quote(pd.DataFrame(quotes), cutoff, config["maximum_sample_age_hours"])
    if status != "available":
        raise ValueError("quote_" + status)
    return row


def kalshi_quote(cache, market, cutoff, config):
    url = KALSHI + "/historical/markets/" + market["ticker"] + "/candlesticks"
    result = cache.get(
        url,
        {
            "start_ts": int(cutoff.timestamp()) - config["quote_lookback_days"] * 86400,
            "end_ts": int(cutoff.timestamp()),
            "period_interval": 60,
        },
    )
    records = []
    for candle in result.json()["candlesticks"]:

        def close(name, candle=candle):
            value = (candle.get(name) or {}).get("close")
            return float(value) if value is not None else np.nan

        records.append(
            {
                "quote_timestamp": pd.Timestamp(candle["end_period_ts"], unit="s", tz="UTC"),
                "bid": close("yes_bid"),
                "ask": close("yes_ask"),
                "trade_close": close("price"),
                "volume": float(candle.get("volume", 0)),
            }
        )
    # Preserve access evidence even for empty responses; no earlier-value fill.
    evidence = {
        "quote_cache_id": result.metadata["cache_id"],
        "quote_retrieved_at": result.metadata["retrieved_at"],
        "source_url": url,
        "returned_samples": len(records),
    }
    try:
        chosen = _selected(records, cutoff, config)
        bid, ask = chosen["bid"], chosen["ask"]
        if not np.isfinite([bid, ask]).all() or not 0 <= bid <= ask <= 1:
            raise ValueError("Missing, invalid or crossed bid/ask")
        if ask - bid > config["kalshi_maximum_spread"] + 1e-12:
            raise ValueError("Spread above prespecified limit")
        return (
            evidence
            | chosen
            | {
                "price": (bid + ask) / 2,
                "spread": ask - bid,
                "zero_sided_book": bid == 0 or ask == 1,
                "quote_update_age_known": False,
                "status": "available",
            }
        )
    except ValueError as error:
        return evidence | {"status": str(error)}


def kalshi_inputs(cache, markets, panel, events, config, metadata_cache_id):
    rows, coverage = [], []
    for row in panel.itertuples():
        cutoff = row.forecast_timestamp
        meeting = events[events.meeting_id == row.meeting_id].iloc[0]
        policy = known_policy(events, cutoff)
        base = {"meeting_id": row.meeting_id, "forecast_timestamp": cutoff, "provider": "kalshi"}
        candidates = [
            m
            for m in markets
            if m["event_ticker"]
            == "FED-" + pd.Timestamp(row.decision_date).strftime("%y%b").upper()
        ]
        try:
            compatible_direction(
                meeting, policy, row.intervening_unscheduled_change, level_target=True
            )
            selected = []
            for offset, role in [(-config["kalshi_grid_step_percent"], "lower"), (0, "current")]:
                strike = float(policy.target_upper_after + offset)
                matches = []
                for market in candidates:
                    rule = market.get("rules_primary", "").replace("**", "")
                    match = re.search(r"greater than\s+(\d+(?:\.\d+)?)%", rule)
                    if (
                        match
                        and "upper bound" in rule.lower()
                        and np.isclose(float(match[1]), strike)
                    ):
                        matches.append(market)
                if len(matches) != 1:
                    raise ValueError(f"Missing or duplicate {role} threshold contract")
                market = matches[0]
                # The retrieved primary rules specify the actual scheduled day.
                stated = re.findall(r"[A-Z][a-z]{2,8} \d{1,2}, \d{4}", market["rules_primary"])
                if not stated or str(pd.Timestamp(stated[-1]).date()) != row.decision_date:
                    raise ValueError("Contract meeting date mismatch/unknown")
                if pd.Timestamp(market["open_time"]) > cutoff:
                    raise ValueError("Contract not open at forecast cutoff")
                quote = kalshi_quote(cache, market, cutoff, config)
                item = (
                    base
                    | {
                        "event_id": market["event_ticker"],
                        "contract_id": market["ticker"],
                        "role": role,
                        "strike": strike,
                        "target_upper_at_forecast": float(policy.target_upper_after),
                        "policy_available_at": policy.label_available_at,
                        "policy_source_url": policy.source_url,
                        "metadata_cache_id": metadata_cache_id,
                        "resolution": market.get("result"),
                        "target_definition": "scheduled_upper_target_level",
                    }
                    | quote
                )
                rows.append(item)
                selected.append(item)
            if any(x["status"] != "available" for x in selected):
                raise ValueError("; ".join(x["role"] + ":" + x["status"] for x in selected))
            threshold_distribution(selected[0]["price"], selected[1]["price"])
            coverage.append(base | {"status": "included", "event_id": selected[0]["event_id"]})
        except (ValueError, SourceUnavailable) as error:
            coverage.append(base | {"status": "excluded", "reason": str(error)})
    return pd.DataFrame(rows), pd.DataFrame(coverage)


def reviewed_poly_event(event, decision_date, expected_rule_hash=None):
    markets = event["markets"]
    if len(markets) != 4 or {m["groupItemTitle"].lower() for m in markets} != set(POLY_BUCKETS):
        raise ValueError("Unreviewed or changed outcome partition")
    rules = {m["description"] for m in markets}
    if len(rules) != 1:
        raise ValueError("Different rules across outcome partition")
    full_rule = next(iter(rules))
    if expected_rule_hash and hashlib.sha256(full_rule.encode()).hexdigest() != expected_rule_hash:
        raise ValueError("Rule text differs from the reviewed version")
    rule = full_rule.lower()
    for required in [
        "upper bound",
        "prior to",
        "rounded up to the nearest 25",
        '"no change" bracket',
    ]:
        if required not in rule:
            raise ValueError("Reviewed rounding/target rules changed")
    if str(pd.Timestamp(event["endDate"]).date()) != decision_date:
        raise ValueError("Contract meeting date mismatch")


def polymarket_inputs(cache, inventory, panel, events, config, metadata_cache_id):
    rows, coverage = [], []
    reviewed = config["polymarket_reviewed_events"]
    for row in panel.itertuples():
        base = {
            "meeting_id": row.meeting_id,
            "forecast_timestamp": row.forecast_timestamp,
            "provider": "polymarket",
        }
        if row.decision_date not in reviewed:
            coverage.append(base | {"status": "excluded", "reason": "No reviewed compatible event"})
            continue
        try:
            event = next((e for e in inventory if e["slug"] == reviewed[row.decision_date]), None)
            if event is None:
                raise ValueError("Reviewed event absent from inventory")
            reviewed_poly_event(
                event, row.decision_date, config["polymarket_rule_sha256"][row.decision_date]
            )
            meeting = events[events.meeting_id == row.meeting_id].iloc[0]
            compatible_direction(
                meeting,
                known_policy(events, row.forecast_timestamp),
                row.intervening_unscheduled_change,
                level_target=False,
            )
            for market in event["markets"]:
                if pd.Timestamp(market["createdAt"]) > row.forecast_timestamp:
                    raise ValueError("Outcome created after forecast cutoff")
                outcomes, tokens = (
                    json.loads(market["outcomes"]),
                    json.loads(market["clobTokenIds"]),
                )
                token = tokens[outcomes.index("Yes")]
                result = cache.get(
                    "https://clob.polymarket.com/prices-history",
                    {
                        "market": token,
                        "startTs": int(row.forecast_timestamp.timestamp())
                        - config["quote_lookback_days"] * 86400,
                        "endTs": int(row.forecast_timestamp.timestamp()),
                        "fidelity": 60,
                    },
                )
                quotes = [
                    {
                        "quote_timestamp": pd.Timestamp(x["t"], unit="s", tz="UTC"),
                        "price": float(x["p"]),
                    }
                    for x in result.json()["history"]
                ]
                item = base | {
                    "event_id": event["id"],
                    "contract_id": market["id"],
                    "token_id": token,
                    "bucket": market["groupItemTitle"].lower(),
                    "target_definition": "scheduled_upper_target_change",
                    "metadata_cache_id": metadata_cache_id,
                    "quote_cache_id": result.metadata["cache_id"],
                    "quote_retrieved_at": result.metadata["retrieved_at"],
                    "source_url": "https://polymarket.com/event/" + event["slug"],
                    "resolution_yes": float(
                        json.loads(market["outcomePrices"])[outcomes.index("Yes")]
                    ),
                    "returned_samples": len(quotes),
                    "quote_update_age_known": False,
                }
                try:
                    item.update(_selected(quotes, row.forecast_timestamp, config))
                    item["status"] = "available"
                except ValueError as error:
                    item["status"] = str(error)
                rows.append(item)
            selected = pd.DataFrame([x for x in rows if x["meeting_id"] == row.meeting_id])
            if not selected.status.eq("available").all():
                raise ValueError("Missing/stale outcome sample")
            partition_distribution(
                selected, reviewed=True, max_sum_error=config["polymarket_maximum_sum_error"]
            )
            coverage.append(
                base
                | {
                    "status": "included",
                    "event_id": event["id"],
                    "raw_price_sum": float(selected.price.sum()),
                }
            )
        except (ValueError, SourceUnavailable) as error:
            coverage.append(base | {"status": "excluded", "reason": str(error)})
    return pd.DataFrame(rows), pd.DataFrame(coverage)
