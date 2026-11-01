"""Independently check saved market forecasts against raw quotes and policy labels."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def verify(root):
    specification = json.loads((root / "specification.json").read_text())
    config = specification["config"]
    panel = pd.read_parquet(root / "input_panel.parquet").set_index("meeting_id")
    quotes = pd.read_parquet(root / "quote_lineage.parquet")
    market = pd.read_parquet(root / "market_predictions.parquet")
    matched = pd.read_parquet(root / "matched_predictions.parquet")
    events = pd.read_parquet(config["meetings"])
    inventory = pd.read_parquet(root / "contract_inventory.parquet").set_index("contract_id")
    truth = panel.target_class
    assert not market.duplicated(["model_name", "meeting_id"]).any()
    assert market.actual_class.equals(market.meeting_id.map(truth).rename("actual_class"))
    raw_cache = {}

    def raw(cache_id):
        if cache_id not in raw_cache:
            body = Path("data/raw") / (cache_id + ".body")
            metadata = json.loads(body.with_suffix(".json").read_text())
            content = body.read_bytes()
            assert hashlib.sha256(content).hexdigest() == metadata["sha256"]
            raw_cache[cache_id] = json.loads(content)
        return raw_cache[cache_id]

    for cache_id in specification["metadata_caches"]:
        raw(cache_id)
    for cache_id in quotes.quote_cache_id.dropna().unique():
        raw(cache_id)
    for prediction in market.itertuples():
        q = quotes[
            (quotes.provider == prediction.model_name)
            & (quotes.meeting_id == prediction.meeting_id)
        ].copy()
        assert q.status.eq("available").all() and q.event_id.nunique() == 1
        assert q.contract_id.nunique() == len(q)
        cutoff = prediction.forecast_timestamp
        assert (q.quote_timestamp <= cutoff).all()
        age = (cutoff - q.quote_timestamp).dt.total_seconds() / 3600
        np.testing.assert_allclose(age, q.quote_age_hours)
        assert age.le(config["maximum_sample_age_hours"]).all()
        meeting = events[events.meeting_id == prediction.meeting_id].iloc[0]
        assert np.isclose(
            meeting.target_upper_before - meeting.target_lower_before,
            meeting.target_upper_after - meeting.target_lower_after,
        )
        if prediction.model_name == "kalshi":
            assert len(q) == 2 and not prediction.intervening_unscheduled_change
            known = (
                events[(events.label_available_at <= cutoff) & events.target_upper_after.notna()]
                .sort_values("label_available_at")
                .iloc[-1]
            )
            for row in q.itertuples():
                assert row.policy_available_at <= cutoff
                assert row.target_upper_at_forecast == known.target_upper_after
                expected_strike = known.target_upper_after - (
                    config["kalshi_grid_step_percent"] if row.role == "lower" else 0
                )
                assert row.strike == expected_strike
                candles = raw(row.quote_cache_id)["candlesticks"]
                past = [x for x in candles if x["end_period_ts"] <= cutoff.timestamp()]
                chosen = max(past, key=lambda x: x["end_period_ts"])
                assert row.quote_timestamp.timestamp() == chosen["end_period_ts"]
                bid, ask = float(chosen["yes_bid"]["close"]), float(chosen["yes_ask"]["close"])
                assert 0 <= bid <= ask <= 1
                assert ask - bid <= config["kalshi_maximum_spread"] + 1e-12
                assert row.price == (bid + ask) / 2
                expected_resolution = "yes" if meeting.target_upper_after > row.strike else "no"
                assert row.resolution == expected_resolution
            by_role = q.set_index("role")
            a, b = by_role.loc["lower", "price"], by_role.loc["current", "price"]
            expected = [1 - a, a - b, b]
        else:
            assert len(q) == 4
            for row in q.itertuples():
                samples = raw(row.quote_cache_id)["history"]
                chosen = max(
                    (x for x in samples if x["t"] <= cutoff.timestamp()), key=lambda x: x["t"]
                )
                assert row.quote_timestamp.timestamp() == chosen["t"] and row.price == chosen["p"]
                definition = json.loads(inventory.loc[row.contract_id, "metadata_json"])
                assert (
                    hashlib.sha256(definition["description"].encode()).hexdigest()
                    == config["polymarket_rule_sha256"][prediction.decision_date]
                )
            total = q.price.sum()
            assert abs(total - 1) <= config["polymarket_maximum_sum_error"]
            classes = q.bucket.map(
                {
                    "50+ bps decrease": "cut",
                    "25 bps decrease": "cut",
                    "no change": "hold",
                    "25+ bps increase": "hike",
                }
            )
            grouped = q.price.groupby(classes).sum() / total
            expected = grouped.reindex(["cut", "hold", "hike"]).to_numpy()
            winners = q[q.resolution_yes.eq(1)]
            assert len(winners) == 1 and classes.loc[winners.index[0]] == prediction.actual_class
        np.testing.assert_allclose(
            expected, [prediction.p_cut, prediction.p_hold, prediction.p_hike]
        )

    tables = pd.read_csv(root / "model_comparison.csv").set_index(["comparison", "model_name"])
    baseline = pd.read_parquet(Path(config["statistical_run"]) / "predictions.parquet")
    baseline = baseline[baseline.model_name == "trees"].set_index("meeting_id")
    classes = ["cut", "hold", "hike"]
    for (cohort, name), frame in matched.groupby(["comparison", "model_name"]):
        assert not frame.meeting_id.duplicated().any()
        p = frame[["p_cut", "p_hold", "p_hike"]].to_numpy()
        assert np.isfinite(p).all() and (p >= 0).all()
        np.testing.assert_allclose(p.sum(axis=1), 1)
        y = np.array([classes.index(label) for label in frame.actual_class])
        brier = ((p - np.eye(3)[y]) ** 2).sum(axis=1)
        loss = -np.log(np.clip(p[np.arange(len(p)), y], config["probability_clip"], 1))
        np.testing.assert_allclose(frame.brier, brier)
        np.testing.assert_allclose(frame.log_loss, loss)
        stored = tables.loc[(cohort, name)]
        np.testing.assert_allclose(
            [stored.brier, stored.log_loss, stored.accuracy],
            [brier.mean(), loss.mean(), (p.argmax(axis=1) == y).mean()],
        )
        assert stored.n == len(frame)
        if name == "trees":
            np.testing.assert_array_equal(
                p, baseline.loc[frame.meeting_id, ["p_cut", "p_hold", "p_hike"]]
            )
        cal = pd.read_csv(root / cohort / "calibration.csv")
        assert cal[cal.model_name == name].groupby("class").n.sum().eq(len(frame)).all()
        if len(frame) < 2 * config["block_length_meetings"]:
            assert cal[cal.model_name == name][["lower_95", "upper_95"]].isna().all().all()
    for cohort, frame in matched.groupby("comparison"):
        sets = [set(x.meeting_id) for _, x in frame.groupby("model_name")]
        assert all(ids == sets[0] for ids in sets)
    differences = pd.read_csv(root / "paired_differences.csv")
    short = differences.n < 2 * config["block_length_meetings"]
    assert differences.loc[short, ["lower_95", "upper_95"]].isna().all().all()
    result = {
        "status": "passed",
        "raw_response_hashes_checked": len(raw_cache),
        "market_forecasts": len(market),
        "unique_real_meetings": market.meeting_id.nunique(),
        "checks": [
            "raw quote values/timestamps and hashes",
            "known policy at issuance",
            "threshold differencing and reviewed partition reconciliation",
            "settlements agree with official targets",
            "unchanged tree probabilities",
            "matched cohorts and independently recomputed metrics",
            "short-sample uncertainty intervals suppressed",
        ],
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/verify_market_baseline.py <run-directory>")
    verify(Path(sys.argv[1]))
