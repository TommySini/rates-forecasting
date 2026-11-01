from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import yaml

from rates_forecasting.data.cache import Cache, SourceUnavailable
from rates_forecasting.data.fed import build_meetings
from rates_forecasting.data.fred import Fred, download_observations
from rates_forecasting.data.markets import audit_markets
from rates_forecasting.evaluation.audit import coverage_report
from rates_forecasting.evaluation.run import evaluate
from rates_forecasting.features.panel import build_panel, feature_names, write_snapshot_audit
from rates_forecasting.paths import dataset_path, prepare_dataset


def snapshot(cache, config):
    decision = config["sample"]["snapshot"]
    from rates_forecasting.time import forecast_time

    cutoff = forecast_time(decision).date().isoformat()
    start = (pd.Timestamp(cutoff) - pd.DateOffset(months=18)).date().replace(day=1).isoformat()
    obs = download_observations(
        cache,
        config["series"],
        start,
        cutoff,
        cutoff,
        dataset_path(config, "interim", "snapshot_observations.parquet"),
        config["availability"].get("unrevised_daily_before_first_vintage", []),
    )
    m = pd.read_parquet("data/interim/meeting_inventory.parquet")
    p, line = build_panel(m, obs, config, only=decision)
    included = [
        f
        for f in feature_names(config["series"])
        if f not in config["models"].get("excluded_features", [])
    ]
    if p[included].isna().any().any():
        raise ValueError("First snapshot incomplete; inspect before scaling")
    snapshot_path = dataset_path(config, "processed", "first_snapshot.parquet")
    p.to_parquet(snapshot_path, index=False)
    line.to_parquet(
        dataset_path(config, "processed", "first_snapshot_lineage.parquet"), index=False
    )
    write_snapshot_audit(p, line, dataset_path(config, "reports", f"snapshot_{decision}.md"))
    if decision == "2019-07-31":
        assert p.payroll_1m.iloc[0] == 224.0 and p.unemployment.iloc[0] == 3.7
    gate = {
        "meeting_id": p.meeting_id.iloc[0],
        "status": "passed",
        "observed_features": len(included),
        "included_features": included,
        "manual_review": config["sample"].get("snapshot_review", "docs/snapshot_review.md"),
        "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
    }
    dataset_path(config, "reports", "snapshot_validation.json").write_text(
        json.dumps(gate, indent=2)
    )


def panel(cache, config):
    gate_path = dataset_path(config, "reports", "snapshot_validation.json")
    if not gate_path.exists() or json.loads(gate_path.read_text()).get("status") != "passed":
        raise ValueError("Reconstruct and audit the first snapshot before scaling")
    expected = json.loads(gate_path.read_text())["snapshot_sha256"]
    if (
        hashlib.sha256(
            dataset_path(config, "processed", "first_snapshot.parquet").read_bytes()
        ).hexdigest()
        != expected
    ):
        raise ValueError("Snapshot changed after validation")
    start = (pd.Timestamp(config["sample"]["start"]) - pd.DateOffset(years=2)).date().isoformat()
    end = config["sample"]["end"]
    obs = download_observations(
        cache,
        config["series"],
        start,
        end,
        end,
        dataset_path(config, "interim", "observations.parquet"),
        config["availability"].get("unrevised_daily_before_first_vintage", []),
    )
    m = pd.read_parquet("data/interim/meeting_inventory.parquet")
    p, line = build_panel(m, obs, config)
    p.to_parquet(dataset_path(config, "processed", "panel.parquet"), index=False)
    line.to_parquet(dataset_path(config, "processed", "lineage.parquet"), index=False)
    print(
        json.dumps(
            coverage_report(
                m, p, line, config, dataset_path(config, "reports", "placeholder").parent
            ),
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Auditable offline FOMC forecasting research")
    parser.add_argument(
        "command",
        choices=[
            "sources",
            "meetings",
            "snapshot",
            "panel",
            "audit",
            "evaluate",
            "sensitivity",
            "markets",
            "all",
        ],
    )
    parser.add_argument("--config", default="configs/baseline.yaml")
    parser.add_argument(
        "--offline", action="store_true", help="Use only immutable cached responses"
    )
    args = parser.parse_args()
    os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache/matplotlib").resolve()))
    config = yaml.safe_load(Path(args.config).read_text())
    prepare_dataset(config)
    cache = Cache(offline=args.offline)
    for directory in ["data/raw", "data/interim", "data/processed", "reports"]:
        Path(directory).mkdir(parents=True, exist_ok=True)
    commands = (
        ["sources", "meetings", "snapshot", "panel", "evaluate", "sensitivity", "markets"]
        if args.command == "all"
        else [args.command]
    )
    try:
        for command in commands:
            if command == "sources":
                f = Fred(cache)
                pd.DataFrame([f.audit_series(sid) for sid in config["series"]]).to_csv(
                    dataset_path(config, "reports", "series_coverage.csv"), index=False
                )
            elif command == "meetings":
                build_meetings(
                    cache, config["sample"]["calendar_start"], int(config["sample"]["end"][:4])
                )
            elif command == "snapshot":
                snapshot(cache, config)
            elif command == "panel":
                panel(cache, config)
            elif command == "audit":
                print(
                    json.dumps(
                        coverage_report(
                            pd.read_parquet("data/interim/meeting_inventory.parquet"),
                            pd.read_parquet(dataset_path(config, "processed", "panel.parquet")),
                            pd.read_parquet(dataset_path(config, "processed", "lineage.parquet")),
                            config,
                            dataset_path(config, "reports", "placeholder").parent,
                        ),
                        indent=2,
                    )
                )
            elif command == "evaluate":
                print(
                    evaluate(
                        pd.read_parquet(dataset_path(config, "processed", "panel.parquet")), config
                    )
                )
            elif command == "sensitivity":
                primary = evaluate(
                    pd.read_parquet(dataset_path(config, "processed", "panel.parquet")), config
                )
                choices = json.loads((primary / "selected_models.json").read_text())
                p, line = build_panel(
                    pd.read_parquet("data/interim/meeting_inventory.parquet"),
                    pd.read_parquet(dataset_path(config, "interim", "observations.parquet")),
                    config,
                    lag=config["availability"]["sensitivity_lag_business_days"],
                )
                p.to_parquet(dataset_path(config, "processed", "panel_lag2.parquet"), index=False)
                line.to_parquet(
                    dataset_path(config, "processed", "lineage_lag2.parquet"), index=False
                )
                variant = config["evaluation"].get("variant", "primary")
                print(
                    evaluate(
                        p,
                        config,
                        variant="lag2" if variant == "primary" else variant + "_lag2",
                        choices=choices,
                    )
                )
            elif command == "markets":
                print(
                    audit_markets(cache)[["platform", "contract_id", "quote_status"]].to_string(
                        index=False
                    )
                )
    except SourceUnavailable as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
