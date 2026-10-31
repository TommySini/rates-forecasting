from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from rates_forecasting.evaluation.metrics import (
    calibration,
    cut_diagnostics,
    paired_differences,
    score_rows,
    summary,
)
from rates_forecasting.evaluation.tuning import cross_validate, resolve_split
from rates_forecasting.features.panel import FEATURES
from rates_forecasting.models.baselines import model


def training_rows(panel, cutoff):
    return panel[(panel.forecast_timestamp < cutoff) & (panel.target_label_available_at < cutoff)]


def walk_forward(panel, name, parameter, config, start, end, features=None):
    rows = []
    targets = panel[(panel.decision_date >= start) & (panel.decision_date < end)].sort_values(
        "forecast_timestamp"
    )
    for _, row in targets.iterrows():
        training = training_rows(panel, row.forecast_timestamp)
        if len(training) < config["sample"]["minimum_train_meetings"]:
            raise ValueError(f"Insufficient initial training for {row.meeting_id}")
        fitted = model(name, parameter, config, features).fit(training)
        p = fitted.predict_proba(pd.DataFrame([row]))[0]
        rows.append(
            {
                "meeting_id": row.meeting_id,
                "forecast_timestamp": row.forecast_timestamp,
                "decision_date": row.decision_date,
                "model_name": name,
                "model_version": f"0.1.0:{json.dumps(parameter, sort_keys=True)}",
                "training_cutoff": training.target_label_available_at.max(),
                "training_n": len(training),
                "p_cut": p[0],
                "p_hold": p[1],
                "p_hike": p[2],
                "actual_class": row.target_class,
                "intervening_unscheduled_change": row.intervening_unscheduled_change,
                "data_kind": "empirical",
            }
        )
    if not rows:
        raise ValueError("No evaluation meetings")
    return pd.DataFrame(rows)


def digest_run(panel, config):
    h = hashlib.sha256(pd.util.hash_pandas_object(panel, index=True).values.tobytes())
    h.update(json.dumps(config, sort_keys=True).encode())
    for path in sorted(Path("src").rglob("*.py")):
        h.update(path.read_bytes())
    h.update(Path("uv.lock").read_bytes())
    return h.hexdigest()


def evaluate(
    panel, config, output_root="reports/runs", features=None, variant="primary", choices=None
):
    if set(panel.data_kind) != {"empirical"}:
        raise ValueError("Synthetic fixtures are prohibited in empirical evaluation")
    features = features or [
        f for f in FEATURES if f not in config["models"].get("excluded_features", [])
    ]
    config, split_ledger, split_summary = resolve_split(panel, config)
    if variant == "primary":
        variant = config["evaluation"].get("variant", variant)
    fingerprint = digest_run(
        panel, config | {"features": features, "variant": variant, "fixed_choices": choices}
    )
    out = Path(output_root) / (variant + "-" + fingerprint[:12])
    if (out / "complete.json").exists():
        return out  # Reproduction reuses immutable results; no silent overwrite.
    out.mkdir(parents=True, exist_ok=True)
    # Freeze the actual training/evaluation cohort, including history-ablation runs.
    panel.to_parquet(out / "input_panel.parquet", index=False)
    split_ledger.to_csv(out / "split_meetings.csv", index=False)
    split_summary.to_csv(out / "split_summary.csv", index=False)
    (out / "resolved_config.json").write_text(json.dumps(config, indent=2))
    sample, ev = config["sample"], config["evaluation"]
    history = Path("reports/evaluation_history.jsonl")
    previous = history.read_text().splitlines() if history.exists() else []
    development = []
    trials = []
    selected = {"frequency": None}
    cut_weight = ev.get("cut_component_weight", 1.0)
    missed_cut_cost = ev.get("missed_cut_cost", 2.0)
    with threadpool_limits(limits=1):
        if choices is None and "search" in ev:
            selected, cv_predictions, cv_table, cv_scores, cv_folds = cross_validate(
                panel, config, features
            )
            cv_predictions.to_parquet(out / "development_candidates.parquet", index=False)
            cv_table.to_csv(out / "cv_candidates.csv", index=False)
            cv_scores.to_csv(out / "cv_fold_scores.csv", index=False)
            cv_folds.to_csv(out / "cv_folds.csv", index=False)
        elif choices is None:
            for name, candidates in [
                ("logistic", config["models"]["logistic_C"]),
                ("trees", config["models"]["tree_l2"]),
            ]:
                scores = []
                for param in candidates:
                    p = walk_forward(
                        panel,
                        name,
                        param,
                        config,
                        sample["development_start"],
                        sample["holdout_start"],
                        features,
                    )
                    p["candidate_parameter"] = param
                    scored = score_rows(p, ev["probability_clip"], cut_weight, missed_cut_cost)
                    trials.append(scored)
                    scores.append((scored.cut_weighted_brier.mean(), param))
                selected[name] = min(scores)[1]
        else:
            selected |= choices
        # Modeling choices are saved before computing any historical holdout score.
        (out / "selected_models.json").write_text(json.dumps(selected, indent=2))
        pd.DataFrame([{"feature": f} for f in features]).to_csv(
            out / "feature_set.csv", index=False
        )
        if trials:
            pd.concat(trials).to_parquet(out / "development_candidates.parquet", index=False)
        entry = {
            "started_at": datetime.now(UTC).isoformat(),
            "fingerprint": fingerprint,
            "variant": variant,
            "selected_models": selected,
            "output": str(out),
            "status": "first_historical_holdout"
            if not previous and variant == "primary"
            else "exploratory_or_prespecified_sensitivity",
            "config": config,
        }
        with history.open("a") as file:
            file.write(json.dumps(entry) + "\n")
        heldout = []
        for name, parameter in selected.items():
            development.append(
                walk_forward(
                    panel,
                    name,
                    parameter,
                    config,
                    sample["development_start"],
                    sample["holdout_start"],
                    features,
                )
            )
            heldout.append(
                walk_forward(
                    panel,
                    name,
                    parameter,
                    config,
                    sample["holdout_start"],
                    str(int(sample["end"][:4]) + 1) + "-01-01",
                    features,
                )
            )
    dev = score_rows(
        pd.concat(development, ignore_index=True),
        ev["probability_clip"],
        cut_weight,
        missed_cut_cost,
    )
    scored = score_rows(
        pd.concat(heldout, ignore_index=True),
        ev["probability_clip"],
        cut_weight,
        missed_cut_cost,
    )
    dev.to_parquet(out / "development_predictions.parquet", index=False)
    scored.to_parquet(out / "predictions.parquet", index=False)
    summary(dev).to_csv(out / "development_comparison.csv", index=False)
    summary(scored).to_csv(out / "model_comparison.csv", index=False)
    summary(scored, ("model_name", "actual_class")).to_csv(out / "by_class.csv", index=False)
    cut_diagnostics(scored).to_csv(out / "cut_diagnostics.csv", index=False)
    cut_diagnostics(dev).to_csv(out / "development_cut_diagnostics.csv", index=False)
    scored["year"] = scored.decision_date.str[:4]
    summary(scored, ("model_name", "year")).to_csv(out / "by_year.csv", index=False)
    scored["period"] = pd.cut(
        scored.year.astype(int),
        [2018, 2020, 2022, 2025],
        labels=["2019–2020", "2021–2022", "2023–2025"],
    )
    summary(scored, ("model_name", "period")).to_csv(out / "by_period.csv", index=False)
    score_sensitivities(scored, out)
    paired_differences(
        scored, ev["bootstrap_replicates"], ev["block_length_meetings"], ev["seed"]
    ).to_csv(out / "paired_differences.csv", index=False)
    cal = calibration(
        scored,
        ev["calibration_bins"],
        ev["bootstrap_replicates"],
        ev["block_length_meetings"],
        ev["seed"],
    )
    cal.to_csv(out / "calibration.csv", index=False)
    scored.sort_values("brier", ascending=False).head(20).to_csv(
        out / "largest_errors.csv", index=False
    )
    from rates_forecasting.evaluation.plots import plots

    plots(scored, cal, out)
    n = scored.meeting_id.nunique()
    always_hold = (scored.drop_duplicates("meeting_id").actual_class == "hold").mean()
    result = {
        "fingerprint": fingerprint,
        "n_holdout_meetings": n,
        "input_panel_sha256": hashlib.sha256(
            (out / "input_panel.parquet").read_bytes()
        ).hexdigest(),
        "always_hold_accuracy": always_hold,
        "brier_convention": "mean over meetings of sum over three classes; range [0,2]; no division by 3",
        "log_loss_clip": ev["probability_clip"],
        "cut_component_weight": cut_weight,
        "missed_cut_cost": missed_cut_cost,
        "selection_objective": "cut_weighted_brier" if cut_weight != 1 else "brier",
        "development_cuts": int(split_summary.set_index("split").loc["development", "cut"]),
        "warnings": [
            "Development has no cuts: cut recall is undefined and tuning cannot establish cut detection."
        ]
        if split_summary.set_index("split").loc["development", "cut"] == 0
        else [],
        "run_status": entry["status"],
        "completed_at": datetime.now(UTC).isoformat(),
    }
    (out / "complete.json").write_text(json.dumps(result, indent=2))
    return out


def score_sensitivities(scored, out):
    pieces = []
    masks = {
        "all": pd.Series(True, index=scored.index),
        "no_intervening_change": scored.intervening_unscheduled_change.eq(False),
        "intervening_change": scored.intervening_unscheduled_change.eq(True),
        "exclude_2020": ~scored.decision_date.str.startswith("2020"),
        "2020_only": scored.decision_date.str.startswith("2020"),
    }
    for name, mask in masks.items():
        frame = scored[mask.fillna(False)]
        if len(frame):
            s = summary(frame)
            s["subset"] = name
            pieces.append(s)
    pd.concat(pieces).to_csv(out / "emergency_sensitivity.csv", index=False)
