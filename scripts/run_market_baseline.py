"""Recover public historical market forecasts and compare frozen shallow trees."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from rates_forecasting.data.cache import Cache
from rates_forecasting.data.market_baseline import (
    POLY_INVENTORY_QUERY,
    kalshi_inputs,
    partition_distribution,
    polymarket_inputs,
    threshold_distribution,
)
from rates_forecasting.data.markets import KALSHI, POLY
from rates_forecasting.evaluation.metrics import (
    calibration,
    cut_diagnostics,
    paired_differences,
    score_rows,
    summary,
)
from rates_forecasting.evaluation.plots import plots


def run(config_path="configs/market_baseline.yaml", offline=False):
    config = yaml.safe_load(Path(config_path).read_text())
    panel = pd.read_parquet(config["panel"])
    panel = panel[panel.decision_date.between(config["test_start"], config["test_end"])].copy()
    if panel.meeting_id.duplicated().any() or not panel.data_kind.eq("empirical").all():
        raise ValueError("Unique empirical meeting panel required")
    events = pd.read_parquet(config["meetings"])
    cache = Cache(offline=offline)
    k = cache.get(KALSHI + "/historical/markets", {"series_ticker": "KXFED", "limit": 1000})
    if k.json().get("cursor"):
        raise ValueError("Kalshi inventory requires additional pagination")
    p = cache.get(POLY + "/events", POLY_INVENTORY_QUERY)
    if len(p.json()) >= POLY_INVENTORY_QUERY["limit"]:
        raise ValueError("Polymarket inventory requires additional pagination")
    print("Reconstructing Kalshi threshold snapshots", flush=True)
    kq, kc = kalshi_inputs(
        cache, k.json()["markets"], panel, events, config, k.metadata["cache_id"]
    )
    print("Reconstructing reviewed Polymarket snapshots", flush=True)
    pq, pc = polymarket_inputs(cache, p.json(), panel, events, config, p.metadata["cache_id"])
    quotes = pd.concat([kq, pq], ignore_index=True)
    coverage = pd.concat([kc, pc], ignore_index=True)
    signature = {
        "config": config,
        "metadata_caches": [k.metadata["cache_id"], p.metadata["cache_id"]],
        "quotes_sha256": hashlib.sha256(quotes.to_json(date_format="iso").encode()).hexdigest(),
        "panel_sha256": hashlib.sha256(Path(config["panel"]).read_bytes()).hexdigest(),
        "meetings_sha256": hashlib.sha256(Path(config["meetings"]).read_bytes()).hexdigest(),
        "baseline_sha256": hashlib.sha256(
            (Path(config["statistical_run"]) / "predictions.parquet").read_bytes()
        ).hexdigest(),
        "sources": {
            str(f): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(Path("src/rates_forecasting").rglob("*.py"))
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "lock_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
    }
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:12]
    out = Path("reports/market_baseline_runs") / fingerprint
    if (out / "complete.json").exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    (out / "specification.json").write_text(json.dumps(signature, indent=2))
    quotes.to_parquet(out / "quote_lineage.parquet", index=False)
    coverage.to_csv(out / "coverage.csv", index=False)
    panel.to_parquet(out / "input_panel.parquet", index=False)
    inventory = [
        {
            "provider": "kalshi",
            "contract_id": m["ticker"],
            "event_id": m["event_ticker"],
            "metadata_cache_id": k.metadata["cache_id"],
            "metadata_json": json.dumps(m),
        }
        for m in k.json()["markets"]
    ] + [
        {
            "provider": "polymarket",
            "contract_id": m["id"],
            "event_id": e["id"],
            "metadata_cache_id": p.metadata["cache_id"],
            "metadata_json": json.dumps(m),
        }
        for e in p.json()
        if e["slug"].startswith(("fed-interest-rates-", "fed-decision-in-"))
        for m in e["markets"]
    ]
    pd.DataFrame(inventory).to_parquet(out / "contract_inventory.parquet", index=False)
    # Choices and eligibility are frozen above; only now join actual outcomes and score.
    predictions = []
    sensitivities = []
    for included in coverage[coverage.status == "included"].itertuples():
        row = panel[panel.meeting_id == included.meeting_id].iloc[0]
        selected = quotes[
            (quotes.provider == included.provider) & (quotes.meeting_id == row.meeting_id)
        ]
        base = {
            "meeting_id": row.meeting_id,
            "forecast_timestamp": row.forecast_timestamp,
            "decision_date": row.decision_date,
            "actual_class": row.target_class,
            "intervening_unscheduled_change": row.intervening_unscheduled_change,
            "model_name": included.provider,
            "model_version": "market-proxy-1",
            "training_cutoff": pd.NaT,
            "data_kind": "empirical_market_probability_proxy",
            "max_sample_age_hours": float(selected.quote_age_hours.max()),
            "quote_update_age_known": False,
        }
        if included.provider == "kalshi":
            selected = selected.set_index("role").loc[["lower", "current"]]
            probability = threshold_distribution(*selected.price)
            if selected.trade_close.notna().all():
                try:
                    trade = threshold_distribution(*selected.trade_close)
                    sensitivities.append(
                        base
                        | {"model_name": "kalshi_trade_close"}
                        | dict(zip(["p_cut", "p_hold", "p_hike"], trade))
                    )
                except ValueError:
                    pass  # Nonmonotone trade prices cannot form a distribution.
        else:
            probability = partition_distribution(
                selected, reviewed=True, max_sum_error=config["polymarket_maximum_sum_error"]
            )
            projected = partition_distribution(
                selected,
                reviewed=True,
                max_sum_error=config["polymarket_maximum_sum_error"],
                method="simplex",
            )
            sensitivities.append(
                base
                | {"model_name": "polymarket_simplex"}
                | dict(zip(["p_cut", "p_hold", "p_hike"], projected))
            )
        predictions.append(base | dict(zip(["p_cut", "p_hold", "p_hike"], probability)))
    if not predictions:
        (out / "complete.json").write_text(json.dumps({"status": "no_eligible_market_forecasts"}))
        return out
    market = score_rows(pd.DataFrame(predictions), config["probability_clip"], 2.0, 2.0)
    market.to_parquet(out / "market_predictions.parquet", index=False)
    trees = pd.read_parquet(Path(config["statistical_run"]) / "predictions.parquet")
    trees = trees[trees.model_name.isin(config["statistical_models"])]
    cohorts, paired, cuts, class_scores = [], [], [], []
    groups = {name: set(frame.meeting_id) for name, frame in market.groupby("model_name")}
    if len(groups) > 1:
        groups["common"] = set.intersection(*groups.values())
    for name, ids in groups.items():
        if not ids:
            continue
        chosen = market[market.meeting_id.isin(ids)]
        if name != "common":
            chosen = chosen[chosen.model_name == name]
        comparison = pd.concat([chosen, trees[trees.meeting_id.isin(ids)]], ignore_index=True)
        assert not comparison.duplicated(["model_name", "meeting_id"]).any()
        assert set(trees[trees.meeting_id.isin(ids)].meeting_id) == ids
        comparison["comparison"] = name
        cohorts.append(comparison)
        differences = paired_differences(
            comparison,
            config["bootstrap_replicates"],
            config["block_length_meetings"],
            config["seed"],
        ).assign(comparison=name)
        enough_blocks = len(ids) >= 2 * config["block_length_meetings"]
        if not enough_blocks:
            differences[["lower_95", "upper_95"]] = np.nan
            differences["method"] = (
                "point differences only: fewer than two prespecified meeting blocks"
            )
        paired.append(differences)
        cuts.append(cut_diagnostics(comparison).assign(comparison=name))
        class_scores.append(
            summary(comparison, ("model_name", "actual_class")).assign(comparison=name)
        )
        folder = out / name
        folder.mkdir(exist_ok=True)
        cal = calibration(
            comparison,
            5,
            config["bootstrap_replicates"],
            config["block_length_meetings"],
            config["seed"],
        )
        note = None
        if not enough_blocks:
            cal[["lower_95", "upper_95"]] = np.nan
            note = "Sample counts only; too few meeting blocks for uncertainty intervals"
        cal.to_csv(folder / "calibration.csv", index=False)
        plots(
            comparison,
            cal,
            folder,
            evaluation_label="exploratory matched market sample",
            calibration_note=note,
        )
    combined = pd.concat(cohorts, ignore_index=True)
    combined.to_parquet(out / "matched_predictions.parquet", index=False)
    summary(combined, ("comparison", "model_name")).to_csv(
        out / "model_comparison.csv", index=False
    )
    pd.concat(paired).to_csv(out / "paired_differences.csv", index=False)
    pd.concat(cuts).to_csv(out / "cut_diagnostics.csv", index=False)
    pd.concat(class_scores).to_csv(out / "by_class.csv", index=False)
    combined.sort_values("brier", ascending=False).head(20).to_csv(
        out / "largest_errors.csv", index=False
    )
    if sensitivities:
        sens = score_rows(pd.DataFrame(sensitivities), config["probability_clip"], 2.0, 2.0)
        sens.to_parquet(out / "sensitivity_predictions.parquet", index=False)
        summary(sens).to_csv(out / "sensitivity_comparison.csv", index=False)
        matched_sensitivities = []
        for name, frame in sens.groupby("model_name"):
            provider = name.split("_")[0]
            ids = set(frame.meeting_id)
            matched = pd.concat(
                [
                    frame,
                    market[(market.model_name == provider) & market.meeting_id.isin(ids)],
                    trees[trees.meeting_id.isin(ids)],
                ],
                ignore_index=True,
            )
            matched_sensitivities.append(summary(matched).assign(comparison=name))
        pd.concat(matched_sensitivities).to_csv(out / "matched_sensitivities.csv", index=False)
    # Internal consistency checks complement the separate synthetic test fixtures.
    for row in market.itertuples():
        q = quotes[(quotes.provider == row.model_name) & (quotes.meeting_id == row.meeting_id)]
        assert q.status.eq("available").all()
        assert (q.quote_timestamp <= row.forecast_timestamp).all()
        assert q.quote_age_hours.le(config["maximum_sample_age_hours"]).all()
    actual = panel.set_index("meeting_id").target_class
    assert market.actual_class.equals(market.meeting_id.map(actual).rename("actual_class"))
    result = {
        "status": "exploratory",
        "fingerprint": fingerprint,
        "test_cohort_meetings": len(panel),
        "included_by_provider": market.groupby("model_name").size().to_dict(),
        "shared_meetings": len(groups.get("common", [])),
        "statistical_models": config["statistical_models"],
        "checks": "unique targets, eligible quote timestamps, finite simplex probabilities, unchanged trees",
        "limitations": [
            "Short selected coverage; no general market accuracy claim",
            "Kalshi threshold conversion assumes 25bp grid and no emergency move",
            "Polymarket prices proportionally reconciled only within reviewed related partitions",
            "Retrospective rule metadata; quote-update age and execution quality unknown",
            "CME credentials/subscription absent; no CME forecasts scored",
        ],
    }
    (out / "complete.json").write_text(json.dumps(result, indent=2))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--config", default="configs/market_baseline.yaml")
    args = parser.parse_args()
    print(run(args.config, args.offline))
