"""Chronological evaluation of the structured reaction model against matched controls."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml
from threadpoolctl import threadpool_limits

from rates_forecasting.evaluation.metrics import (
    calibration,
    cut_diagnostics,
    paired_differences,
    score_rows,
    summary,
)
from rates_forecasting.evaluation.plots import plots
from rates_forecasting.evaluation.run import digest_run, training_rows
from rates_forecasting.evaluation.tuning import development_folds, resolve_split
from rates_forecasting.models.baselines import model
from rates_forecasting.models.policy import INPUTS, OrderedFree, TaylorOrdered, WeakOrdered
from rates_forecasting.paths import dataset_path

TAYLOR_MODELS = {"taylor_ordered": "taylor", "taylor_wrong_prior": "wrong"}


def build(name, value, config, specification):
    if name in TAYLOR_MODELS:
        priors = specification["priors"]
        return TaylorOrdered(value, priors[TAYLOR_MODELS[name]], priors["sd"])
    if name in specification.get("weak_models", {}):
        return WeakOrdered(specification["weak_models"][name])
    if name == "ordered_free":
        return OrderedFree(value)
    if name == "small_logistic":
        return model("logistic", {"C": value}, config, INPUTS)
    raise ValueError(name)


def references(specification):
    """Frozen comparison forecasts as (run, file, {source name: reported name})."""
    if "references" in specification:
        return [(r["run"], r["file"], r["models"]) for r in specification["references"]]
    baseline = specification["baseline_run"]
    names = pd.read_parquet(Path(baseline) / "predictions.parquet").model_name.unique()
    world = {name: name for name in specification["world_models"]}
    return [
        (baseline, "predictions.parquet", {name: name for name in names}),
        (specification["world_run"], "world_predictions.parquet", world),
    ]


def load_references(specification, columns):
    frames = []
    for run, file, names in references(specification):
        frame = pd.read_parquet(Path(run) / file)
        frame = frame[frame.model_name.isin(names)].copy()
        frame["model_name"] = frame.model_name.map(names)
        frames.append(frame[columns])
    return pd.concat(frames, ignore_index=True)


def predict(training, forecast, name, value, config, specification):
    start = specification.get("training_start", {}).get(name)
    if start:
        training = training[training.decision_date >= start]
    fitted = build(name, value, config, specification).fit(training)
    result = forecast[
        ["meeting_id", "forecast_timestamp", "decision_date", "intervening_unscheduled_change"]
    ].copy()
    result["actual_class"] = forecast.target_class
    result["model_name"] = name
    result["model_version"] = f"policy-1:{value}"
    result["training_n"] = len(training)
    result["training_cutoff"] = training.target_label_available_at.max()
    result["data_kind"] = "empirical_prediction"
    result[["p_cut", "p_hold", "p_hike"]] = fitted.predict_proba(forecast)
    return result, fitted


def select(table):
    """Lowest cut-weighted Brier, then standard Brier, then the smaller grid value."""
    return {
        name: float(frame.sort_values(["cut_weighted_brier", "brier", "value"]).iloc[0].value)
        for name, frame in table.groupby("model_name")
    }


def run_policy(config_path="configs/policy_model.yaml"):
    specification = yaml.safe_load(Path(config_path).read_text())
    config = yaml.safe_load(Path(specification["base_config"]).read_text())
    panel = pd.read_parquet(dataset_path(config, "processed", "panel.parquet"))
    if set(panel.data_kind) != {"empirical"}:
        raise ValueError("Empirical panel required; synthetic rows cannot enter evaluation")
    config, split, split_summary = resolve_split(panel, config)
    ev = config["evaluation"]
    score = lambda p: score_rows(
        p, ev["probability_clip"], ev["cut_component_weight"], ev["missed_cut_cost"]
    )
    signature = specification | {"base": config, "inputs": INPUTS}
    fingerprint = digest_run(panel, signature)
    out = Path("reports/policy_model_runs") / fingerprint[:12]
    if (out / "complete.json").exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    split.to_csv(out / "split_meetings.csv", index=False)
    split_summary.to_csv(out / "split_summary.csv", index=False)
    (out / "specification.json").write_text(json.dumps(signature, indent=2, default=str))
    grids = specification["grids"]
    cv_predictions = []
    with threadpool_limits(limits=1):
        for fold, train, validation in development_folds(panel, config):
            for name, values in grids.items():
                for value in values:
                    prediction, _ = predict(train, validation, name, value, config, specification)
                    prediction = score(prediction)
                    prediction["fold"], prediction["value"] = fold, value
                    cv_predictions.append(prediction)
        candidates = pd.concat(cv_predictions, ignore_index=True)
        table = candidates.groupby(["model_name", "value"], as_index=False).agg(
            n=("brier", "size"),
            brier=("brier", "mean"),
            cut_weighted_brier=("cut_weighted_brier", "mean"),
            log_loss=("log_loss", "mean"),
        )
        selected = select(table)
        candidates.to_parquet(out / "cv_predictions.parquet", index=False)
        table.to_csv(out / "cv_candidates.csv", index=False)
        (out / "selected_models.json").write_text(json.dumps(selected, indent=2))
        # Freeze all choices before any test scores are computed.
        entry = {
            "started_at": datetime.now(UTC).isoformat(),
            "status": "exploratory",
            "fingerprint": fingerprint,
            "selected": selected,
            "output": str(out),
        }
        with Path("reports/policy_model_evaluation_history.jsonl").open("a") as file:
            file.write(json.dumps(entry) + "\n")
        test = panel[panel.decision_date >= config["sample"]["holdout_start"]].sort_values(
            "forecast_timestamp"
        )
        test_predictions, parameters = [], []
        for _, row in test.iterrows():
            train = training_rows(panel, row.forecast_timestamp)
            forecast = pd.DataFrame([row])
            for name, value in selected.items():
                prediction, fitted = predict(train, forecast, name, value, config, specification)
                test_predictions.append(prediction)
                if hasattr(fitted, "parameters"):
                    gap = (
                        {"rule_gap": float(fitted.gap(forecast)[0])}
                        if name in TAYLOR_MODELS
                        else {}
                    )
                    parameters.append(
                        {
                            "meeting_id": row.meeting_id,
                            "model_name": name,
                            "strength": value,
                            "training_n": int(prediction.training_n.iloc[0]),
                            **gap,
                            **fitted.parameters(),
                        }
                    )
    fresh = score(pd.concat(test_predictions, ignore_index=True))
    fresh.to_parquet(out / "policy_predictions.parquet", index=False)
    pd.DataFrame(parameters).to_csv(out / "test_parameters.csv", index=False)
    columns = list(fresh.columns)
    frozen = load_references(specification, columns)
    for name, frame in frozen.groupby("model_name"):
        if set(frame.meeting_id) != set(fresh.meeting_id) or len(frame) != len(test):
            raise ValueError(f"Frozen reference {name} must share the test meetings")
    combined = pd.concat([frozen, fresh[columns]], ignore_index=True)
    combined.to_parquet(out / "predictions.parquet", index=False)
    summary(combined).to_csv(out / "model_comparison.csv", index=False)
    summary(combined, ("model_name", "actual_class")).to_csv(out / "by_class.csv", index=False)
    cut_diagnostics(combined).to_csv(out / "cut_diagnostics.csv", index=False)
    paired_differences(
        combined, ev["bootstrap_replicates"], ev["block_length_meetings"], ev["seed"]
    ).to_csv(out / "paired_differences.csv", index=False)
    # Ex-ante subset: the previous scheduled decision was a hold, so a move would
    # end a pause. Defined from issuance information, never from the outcome.
    after_hold = set(test.loc[test.previous_scheduled_bps == 0, "meeting_id"])
    paused = combined[combined.meeting_id.isin(after_hold)]
    summary(paused).to_csv(out / "after_hold_comparison.csv", index=False)
    paired_differences(
        paused, ev["bootstrap_replicates"], ev["block_length_meetings"], ev["seed"]
    ).to_csv(out / "after_hold_paired_differences.csv", index=False)
    cal = calibration(
        combined,
        ev["calibration_bins"],
        ev["bootstrap_replicates"],
        ev["block_length_meetings"],
        ev["seed"],
    )
    cal.to_csv(out / "calibration.csv", index=False)
    combined.sort_values("brier", ascending=False).head(25).to_csv(
        out / "largest_errors.csv", index=False
    )
    plots(combined, cal, out, evaluation_label="exploratory test")
    (out / "complete.json").write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "status": "exploratory",
                "real_test_meetings": len(test),
                "synthetic_test_meetings": 0,
                "selected": selected,
                "completed_at": datetime.now(UTC).isoformat(),
                "limitations": [
                    "Constant neutral rate and unemployment benchmark over 2000-2025",
                    "Core CPI stands in for the Fed's PCE inflation target",
                    "26 test meetings; test years examined in earlier experiments",
                ],
            },
            indent=2,
        )
    )
    return out
