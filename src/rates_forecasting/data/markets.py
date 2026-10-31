"""Read-only contract coverage audit. No trading or automatic probability normalization."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from rates_forecasting.data.cache import SourceUnavailable
from rates_forecasting.time import forecast_time

KALSHI = "https://external-api.kalshi.com/trade-api/v2"
POLY = "https://gamma-api.polymarket.com"


def last_quote(quotes, cutoff, max_age_hours=24):
    if quotes.empty:
        return None, "missing"
    rows = quotes[quotes.quote_timestamp <= cutoff].sort_values("quote_timestamp")
    if rows.empty:
        return None, "missing"
    row = rows.iloc[-1]
    age = (cutoff - row.quote_timestamp).total_seconds() / 3600
    return row.to_dict() | {"quote_age_hours": age}, "stale" if age > max_age_hours else "available"


def map_distribution(contracts, *, target_definition, mutually_exclusive, exhaustive):
    """Only explicit compatible partitions may be summed. Never renormalize quotes."""
    if target_definition != "scheduled_meeting_change" or not mutually_exclusive or not exhaustive:
        raise ValueError("Compatible mutually exclusive and exhaustive outcomes required")
    if set(contracts.outcome_class) != {"cut", "hold", "hike"}:
        raise ValueError("Incomplete outcome mapping")
    if contracts.contract_id.duplicated().any() or contracts.price.isna().any():
        raise ValueError("Duplicate contract or missing price")
    if not np.isfinite(contracts.price).all() or not contracts.price.between(0, 1).all():
        raise ValueError("Invalid market price")
    if (
        "target_definition" in contracts
        and not contracts.target_definition.eq(target_definition).all()
    ):
        raise ValueError("Mixed rate-level and change contracts")
    p = contracts.groupby("outcome_class").price.sum().reindex(["cut", "hold", "hike"])
    if not np.isclose(p.sum(), 1, atol=0.01):
        raise ValueError(
            "Prices do not form a probability distribution; do not normalize mechanically"
        )
    return p.to_dict()


def audit_markets(cache):
    rows, access = [], []
    fields = [
        "platform",
        "event_id",
        "contract_id",
        "question",
        "full_resolution_rules",
        "meeting_mapping",
        "outcome_mapping",
        "quote_timestamp",
        "price",
        "bid",
        "ask",
        "volume",
        "resolution",
        "source",
    ]
    for event, decision in [
        ("KXFEDDECISION-24SEP", "2024-09-18"),
        ("KXFEDDECISION-25SEP", "2025-09-17"),
    ]:
        cutoff = pd.Timestamp(forecast_time(decision))
        try:
            r = cache.get(KALSHI + "/historical/markets", {"event_ticker": event, "limit": 100})
            markets = r.json()["markets"]
            access.append(
                {
                    "platform": "Kalshi",
                    "event": event,
                    "contracts_returned": len(markets),
                    "retrieved_at": r.metadata["retrieved_at"],
                    "cache_id": r.metadata["cache_id"],
                }
            )
            for m in markets:
                suffix = m["ticker"].split("-")[-1]
                mapping = "hold" if suffix == "H0" else "hike" if suffix.startswith("H") else "cut"
                row = dict.fromkeys(fields)
                row.update(
                    platform="Kalshi",
                    event_id=event,
                    contract_id=m["ticker"],
                    question=m["title"],
                    full_resolution_rules=m.get("rules_primary", "")
                    + "\n"
                    + m.get("rules_secondary", ""),
                    meeting_mapping="FOMC-" + decision,
                    outcome_mapping=mapping,
                    resolution=m.get("result"),
                    source=KALSHI + "/historical/markets/" + m["ticker"],
                    forecast_timestamp=cutoff,
                    quote_status="missing",
                    quote_age_hours=None,
                    mapping_status="candidate_only; rules require review; 25bp grid not guaranteed",
                    retrieved_at=r.metadata["retrieved_at"],
                    metadata_cache_id=r.metadata["cache_id"],
                )
                try:
                    candles = cache.get(
                        row["source"] + "/candlesticks",
                        {
                            "start_ts": int(cutoff.timestamp()) - 7 * 86400,
                            "end_ts": int(cutoff.timestamp()),
                            "period_interval": 60,
                        },
                    )
                    records = []
                    for c in candles.json()["candlesticks"]:

                        def close(field, c=c):
                            val = (c.get(field) or {}).get("close")
                            return float(val) if val is not None else None

                        records.append(
                            {
                                "quote_timestamp": pd.Timestamp(
                                    c["end_period_ts"], unit="s", tz="UTC"
                                ),
                                "price": close("price"),
                                "bid": close("yes_bid"),
                                "ask": close("yes_ask"),
                                "volume": float(c.get("volume", 0)),
                            }
                        )
                    quotes = pd.DataFrame(records)
                    if len(quotes):
                        quotes = quotes[
                            quotes.price.notna() | quotes.bid.notna() | quotes.ask.notna()
                        ]
                    quote, status = last_quote(quotes, cutoff)
                    row["quote_status"] = status
                    if quote:
                        row.update(quote)
                    row["quote_cache_id"] = candles.metadata["cache_id"]
                    row["quote_limitation"] = (
                        "Hourly candle close; not an executable quote or a verified last-update timestamp"
                    )
                except SourceUnavailable as error:
                    row["quote_status"] = str(error)
                rows.append(row)
        except SourceUnavailable as error:
            access.append({"platform": "Kalshi", "event": event, "error": str(error)})
    slug, decision = "fed-interest-rates-september-2024", "2024-09-18"
    cutoff = pd.Timestamp(forecast_time(decision))
    try:
        r = cache.get(POLY + "/events", {"slug": slug})
        events = r.json()
        access.append(
            {
                "platform": "Polymarket",
                "event": slug,
                "events_returned": len(events),
                "retrieved_at": r.metadata["retrieved_at"],
                "cache_id": r.metadata["cache_id"],
            }
        )
        for event in events:
            for m in event["markets"]:
                title = m["groupItemTitle"].lower()
                mapping = (
                    "cut" if "decrease" in title else "hike" if "increase" in title else "hold"
                )
                outcomes = json.loads(m["outcomes"])
                token = json.loads(m["clobTokenIds"])[outcomes.index("Yes")]
                prices = json.loads(m["outcomePrices"])
                row = dict.fromkeys(fields)
                row.update(
                    platform="Polymarket",
                    event_id=event["id"],
                    contract_id=m["id"],
                    token_id=token,
                    question=m["question"],
                    full_resolution_rules=m["description"],
                    meeting_mapping="FOMC-" + decision,
                    outcome_mapping=mapping,
                    resolution="Yes"
                    if prices[outcomes.index("Yes")] == "1"
                    else "No"
                    if prices[outcomes.index("Yes")] == "0"
                    else None,
                    source=f"https://polymarket.com/event/{slug}",
                    forecast_timestamp=cutoff,
                    quote_status="missing",
                    quote_age_hours=None,
                    mapping_status="candidate_only; upper-bound target, rule wording ambiguity, non-25bp gaps",
                    retrieved_at=r.metadata["retrieved_at"],
                    metadata_cache_id=r.metadata["cache_id"],
                )
                try:
                    history = cache.get(
                        "https://clob.polymarket.com/prices-history",
                        {
                            "market": token,
                            "startTs": int(cutoff.timestamp()) - 7 * 86400,
                            "endTs": int(cutoff.timestamp()),
                            "fidelity": 60,
                        },
                    )
                    quotes = pd.DataFrame(
                        [
                            {
                                "quote_timestamp": pd.Timestamp(x["t"], unit="s", tz="UTC"),
                                "price": float(x["p"]),
                            }
                            for x in history.json()["history"]
                        ]
                    )
                    quote, status = last_quote(quotes, cutoff)
                    row["quote_status"] = status
                    if quote:
                        row.update(quote)
                    row["quote_cache_id"] = history.metadata["cache_id"]
                    row["quote_limitation"] = (
                        "Price-only history; no historical bid, ask, or interval volume"
                    )
                except SourceUnavailable as error:
                    row["quote_status"] = str(error)
                rows.append(row)
    except SourceUnavailable as error:
        access.append({"platform": "Polymarket", "event": slug, "error": str(error)})
    out = Path("data/processed")
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if len(frame):
        frame["quote_timestamp"] = pd.to_datetime(frame.quote_timestamp, utc=True)
        frame.to_parquet(out / "market_contract_audit.parquet", index=False)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/market_access.json").write_text(
        json.dumps({"audited_at": datetime.now(UTC).isoformat(), "requests": access}, indent=2)
    )
    frame.drop(columns=["full_resolution_rules"], errors="ignore").to_csv(
        "reports/market_coverage.csv", index=False
    )
    return frame
