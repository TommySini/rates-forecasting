"""Coverage, exclusions, source availability, and leakage reports."""

import json
from pathlib import Path

from rates_forecasting.evaluation.tuning import resolve_split
from rates_forecasting.features.panel import intervening_change, panel_features, validate_panel
from rates_forecasting.time import forecast_time


def coverage_report(meetings, panel, lineage, config, output="reports"):
    config, _, _ = resolve_split(panel, config)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    validate_panel(panel, lineage, meetings)
    features = panel_features(panel)
    by_year = (
        panel.assign(year=panel.decision_date.str[:4])
        .groupby(["year", "target_class"])
        .size()
        .unstack(fill_value=0)
    )
    by_year.to_csv(out / "coverage_by_year.csv")
    missing = panel[features].isna().sum().rename("missing_n").to_frame()
    missing["missing_fraction"] = missing.missing_n / len(panel)
    missing["in_primary_model"] = ~missing.index.isin(config["models"].get("excluded_features", []))
    missing.to_csv(out / "feature_missingness.csv")
    lineage.groupby(["feature", "quality"]).size().rename("n").to_csv(
        out / "availability_quality.csv"
    )
    exclusions = meetings[~meetings.meeting_id.isin(panel.meeting_id)].copy()
    exclusions["reason"] = exclusions.apply(
        lambda r: (
            r.scheduled_status
            if r.scheduled_status != "scheduled"
            else "before_primary_vintage_coverage"
            if r.decision_date < config["sample"]["start"]
            else r.verification_status
        ),
        axis=1,
    )
    exclusions["forecast_timestamp"] = exclusions.scheduled_decision_date.map(forecast_time)
    exclusions["intervening_unscheduled_change"] = [
        intervening_change(meetings, t, d)
        for t, d in zip(exclusions.forecast_timestamp, exclusions.scheduled_decision_date)
    ]
    exclusions[
        [
            "meeting_id",
            "scheduled_decision_date",
            "scheduled_status",
            "reason",
            "forecast_timestamp",
            "intervening_unscheduled_change",
            "calendar_source_url",
        ]
    ].to_csv(out / "exclusions.csv", index=False)
    methods = {}
    for text in lineage.inputs_json:
        for item in json.loads(text):
            method = item["availability_method"]
            methods[method] = methods.get(method, 0) + 1
    selected = [f for f in features if f not in config["models"].get("excluded_features", [])]
    result = {
        "status": "passed",
        "sample_start": panel.decision_date.min(),
        "sample_end": panel.decision_date.max(),
        "meetings": len(panel),
        "candidate_features": len(features),
        "model_features": len(selected),
        "class_counts": panel.target_class.value_counts().to_dict(),
        "training_meetings": int(
            (panel.decision_date < config["sample"]["development_start"]).sum()
        ),
        "development_meetings": int(
            (
                (panel.decision_date >= config["sample"]["development_start"])
                & (panel.decision_date < config["sample"]["holdout_start"])
            ).sum()
        ),
        "holdout_meetings": int((panel.decision_date >= config["sample"]["holdout_start"]).sum()),
        "missing_model_feature_cells": int(panel[selected].isna().sum().sum()),
        "unknown_decision_publication_times": int(panel.target_decision_timestamp.isna().sum()),
        "intervening_unscheduled_changes": int(
            panel.intervening_unscheduled_change.fillna(False).sum()
        ),
        "unknown_intervening_flags": int(panel.intervening_unscheduled_change.isna().sum()),
        "input_lineage_rows": sum(methods.values()),
        "input_availability_methods": methods,
        "checks": [
            "unique meeting/horizon",
            "feature/input availability <= issuance",
            "forecast < decision/label availability",
            "target equals sourced announcement label",
            "complete feature lineage",
            "explicit missing values",
        ],
        "limitations": [
            "Archive-date uncertainty persists under conservative lag",
            "Historical schedules are retrospective; not separately archived at each issuance",
            "Early announcement times remain unknown; training eligibility uses conservative next-day lag",
            "Cancelled meetings have no cut/hold/hike target and remain in the exclusions ledger",
        ],
    }
    (out / "data_quality_audit.json").write_text(json.dumps(result, indent=2))
    return result
