"""Chronological world-model pilot. Synthetic draws never become empirical rows."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from math import erf, exp, log, pi, sqrt
from pathlib import Path

import numpy as np
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
from rates_forecasting.features.panel import FEATURES
from rates_forecasting.models.world import (
    CHANNELS,
    SERIES,
    LinearWorld,
    MacroHistory,
    WorldClassifier,
)
from rates_forecasting.paths import dataset_path


def prepare_world(training, forecast, history, specification):
    # Parameter fitting stops at the last training feature timestamp. Validation
    # releases may update the filtered state, but never normalization/dynamics.
    parameter_cutoff = training.forecast_timestamp.max()
    world = LinearWorld(**specification["world"]).fit(history.at(parameter_cutoff))
    results = []
    for frame in (training, forecast):
        means, covariances, lags, audit = [], [], [], []
        for row in frame.itertuples():
            snapshot = history.at(row.forecast_timestamp)
            mean, cov = world.moments(snapshot)
            means.append(mean)
            covariances.append(cov)
            lags.append(
                snapshot.values.tail(specification["classifier"]["history_months"])
                .to_numpy()
                .ravel()
            )
            audit.append(
                {
                    "meeting_id": row.meeting_id,
                    "forecast_timestamp": row.forecast_timestamp,
                    "state_input_max_available_at": snapshot.max_available_at,
                    "eligible_series_months": snapshot.eligible_versions,
                    "world_parameter_cutoff": world.fit_cutoff,
                    "world_parameter_max_available_at": world.max_fit_available_at,
                    "world_fit_months": world.fit_months,
                    "state_mean_json": json.dumps(mean.tolist()),
                    "state_covariance_json": json.dumps(cov.tolist()),
                }
            )
        results.append(
            (np.asarray(means), np.asarray(covariances), np.asarray(lags), pd.DataFrame(audit))
        )
    return world, results[0], results[1]


def classifier(mode, C, features, config, specification):
    options = specification["classifier"]
    return WorldClassifier(
        mode,
        C,
        features,
        config["evaluation"]["seed"],
        options["train_draws"],
        options["prediction_draws"],
        options["noise_scale"],
    )


def predict(training, forecast, train_info, forecast_info, head):
    means, covariances, lags, _ = train_info
    head.fit(training, means, covariances, lags)
    means, covariances, lags, audit = forecast_info
    p = head.predict_proba(forecast, means, covariances, lags)
    result = forecast[
        ["meeting_id", "forecast_timestamp", "decision_date", "intervening_unscheduled_change"]
    ].copy()
    result["actual_class"] = forecast.target_class
    result["model_name"] = head.mode
    result["model_version"] = f"world-pilot-1:C={head.C}"
    result["training_n"] = len(training)
    result["training_cutoff"] = training.target_label_available_at.max()
    result["total_training_weight"] = head.total_training_weight
    result["data_kind"] = "empirical_prediction"
    result[["p_cut", "p_hold", "p_hike"]] = p
    for column in [
        "state_input_max_available_at",
        "world_parameter_cutoff",
        "world_parameter_max_available_at",
        "world_fit_months",
    ]:
        result[column] = audit[column].to_numpy()
    return result


def release_window_audit(panel, observations):
    # Ex-post coverage descriptor only; never input to model fitting or forecasts.
    first = observations.sort_values("available_at").drop_duplicates(
        ["series_id", "observation_period"]
    )
    rows = []
    for row in panel.itertuples():
        stop = pd.Timestamp(row.decision_date, tz="America/New_York").tz_convert("UTC")
        events = first[(first.available_at > row.forecast_timestamp) & (first.available_at < stop)]
        rows.append(
            {
                "meeting_id": row.meeting_id,
                "new_series_months": len(events),
                "new_labor_inflation_series_months": int(events.series_id.ne("INDPRO").sum()),
                "usage": "ex_post_descriptive_only",
            }
        )
    return pd.DataFrame(rows)


def release_predictions(world, snapshot, meeting_id):
    """Predict each series' next unreported transformed month, without its calendar."""
    means, covariances = world.filter(snapshot)
    adjacent = np.diff(world.training_periods.asi8) == 1
    innovations = np.diff(world.training_standardized, axis=0)[adjacent]
    persistence_variance = np.maximum(innovations.var(axis=0, ddof=1), 1e-8) * world.scale**2
    rows = []
    for k, (channel, series) in enumerate(zip(CHANNELS, SERIES)):
        latest = snapshot.values[channel].last_valid_index()
        if latest is None:
            continue
        target = latest + 1
        if target in snapshot.values.index:
            index = snapshot.values.index.get_loc(target)
            mean, cov = means[index], covariances[index]
        else:
            mean, cov = means[-1].copy(), covariances[-1].copy()
            for _ in range(target.ordinal - snapshot.values.index[-1].ordinal):
                mean, cov = world.F @ mean, world.F @ cov @ world.F.T + world.Q
        for name, mu, variance in [
            (
                "world",
                world.center[k] + world.scale[k] * (world.H[k] @ mean),
                world.scale[k] ** 2 * (world.H[k] @ cov @ world.H[k] + world.R[k]),
            ),
            ("persistence", snapshot.values.loc[latest, channel], persistence_variance[k]),
        ]:
            rows.append(
                {
                    "meeting_id": meeting_id,
                    "forecast_timestamp": snapshot.cutoff,
                    "model_name": name,
                    "channel": channel,
                    "series_id": series,
                    "target_period": str(target),
                    "mean": float(mu),
                    "variance": float(variance),
                    "training_scale": float(world.scale[k]),
                    "parameter_cutoff": world.fit_cutoff,
                }
            )
    return rows


def gaussian_crps(actual, mean, variance):
    sigma = sqrt(variance)
    z = (actual - mean) / sigma
    cdf = (1 + erf(z / sqrt(2))) / 2
    density = exp(-z * z / 2) / sqrt(2 * pi)
    return sigma * (z * (2 * cdf - 1) + 2 * density - 1 / sqrt(pi))


def score_releases(predictions, history):
    # Called only after all Fed forecasts/settings are frozen. Future actuals are
    # targets for this separate diagnostic, never inputs to model fitting.
    first = history.observations.sort_values("available_at").drop_duplicates(
        ["series_id", "observation_period"]
    )
    first = first.set_index(["series_id", "observation_period"])
    rows = []
    for row in predictions:
        row = dict(row)
        key = (row["series_id"], row["target_period"] + "-01")
        if key not in first.index:
            row["target_status"] = "not_in_archive"
        else:
            available = first.loc[key, "available_at"]
            row["target_available_at"] = available
            if available <= row["forecast_timestamp"]:
                row["target_status"] = "already_available_or_missing_derived_value"
            else:
                actual = history.at(available).values.loc[
                    pd.Period(row["target_period"], freq="M"), row["channel"]
                ]
                if not np.isfinite(actual):
                    row["target_status"] = "missing_derived_value"
                else:
                    row["target_status"] = "scored"
                    row["actual"] = float(actual)
                    row["crps"] = gaussian_crps(actual, row["mean"], row["variance"])
                    row["standardized_crps"] = row["crps"] / row["training_scale"]
                    row["negative_log_density"] = 0.5 * (
                        log(2 * pi * row["variance"])
                        + (actual - row["mean"]) ** 2 / row["variance"]
                    )
                    # Numeric 0/1 avoids object-dtype numpy-bool aggregation when
                    # unscoreable targets introduce missing entries in this column.
                    row["covered_90"] = float(
                        abs(actual - row["mean"]) <= 1.6448536269514722 * sqrt(row["variance"])
                    )
        rows.append(row)
    return pd.DataFrame(rows)


def run_world(config_path="configs/world_model.yaml"):
    specification = yaml.safe_load(Path(config_path).read_text())
    config = yaml.safe_load(Path(specification["base_config"]).read_text())
    panel = pd.read_parquet(dataset_path(config, "processed", "panel.parquet"))
    if set(panel.data_kind) != {"empirical"}:
        raise ValueError("Empirical panel required; synthetic rows cannot enter evaluation")
    observations_path = dataset_path(config, "interim", "observations.parquet")
    observations = pd.read_parquet(observations_path)
    config, split, split_summary = resolve_split(panel, config)
    features = [f for f in FEATURES if f not in config["models"]["excluded_features"]]
    ev = config["evaluation"]
    score = lambda p: score_rows(
        p, ev["probability_clip"], ev["cut_component_weight"], ev["missed_cut_cost"]
    )
    signature = specification | {
        "base": config,
        "observations_sha256": hashlib.sha256(observations_path.read_bytes()).hexdigest(),
    }
    fingerprint = digest_run(panel, signature)
    out = Path("reports/world_model_runs") / fingerprint[:12]
    if (out / "complete.json").exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    split.to_csv(out / "split_meetings.csv", index=False)
    split_summary.to_csv(out / "split_summary.csv", index=False)
    panel.to_parquet(out / "input_panel.parquet", index=False)
    (out / "specification.json").write_text(json.dumps(signature, indent=2))
    release_window_audit(panel, observations).to_csv(
        out / "release_window_coverage.csv", index=False
    )
    history = MacroHistory(observations)
    modes = specification["classifier"]["modes"]
    cv_predictions, fold_audits, test_predictions, moment_audits = [], [], [], []
    macro_predictions = []
    # The world and classifiers are fitted wholly within each development fold.
    with threadpool_limits(limits=1):
        for fold, train, validation in development_folds(panel, config):
            world, train_info, val_info = prepare_world(train, validation, history, specification)
            for mode in modes:
                for C in specification["classifier"]["C"]:
                    head = classifier(mode, C, features, config, specification)
                    prediction = score(predict(train, validation, train_info, val_info, head))
                    prediction["fold"], prediction["C"] = fold, C
                    cv_predictions.append(prediction)
            audit = val_info[3].copy()
            audit["fold"] = fold
            fold_audits.append(audit)
            print(
                f"Development fold {fold}: {len(train)} real decisions, {world.fit_months} macro months",
                flush=True,
            )
        candidates = pd.concat(cv_predictions, ignore_index=True)
        table = candidates.groupby(["model_name", "C"], as_index=False).agg(
            n=("brier", "size"),
            brier=("brier", "mean"),
            cut_weighted_brier=("cut_weighted_brier", "mean"),
            log_loss=("log_loss", "mean"),
        )
        selected = {
            name: float(frame.sort_values(["cut_weighted_brier", "brier", "C"]).iloc[0].C)
            for name, frame in table.groupby("model_name")
        }
        candidates.to_parquet(out / "cv_predictions.parquet", index=False)
        table.to_csv(out / "cv_candidates.csv", index=False)
        pd.concat(fold_audits).to_parquet(out / "cv_state_audit.parquet", index=False)
        (out / "selected_models.json").write_text(json.dumps(selected, indent=2))
        # Freeze all choices before any test scores are computed.
        entry = {
            "started_at": datetime.now(UTC).isoformat(),
            "status": "exploratory",
            "fingerprint": fingerprint,
            "selected": selected,
            "output": str(out),
        }
        with Path("reports/world_model_evaluation_history.jsonl").open("a") as file:
            file.write(json.dumps(entry) + "\n")
        test = panel[panel.decision_date >= config["sample"]["holdout_start"]].sort_values(
            "forecast_timestamp"
        )
        for index, (_, row) in enumerate(test.iterrows()):
            train = training_rows(panel, row.forecast_timestamp)
            validation = pd.DataFrame([row])
            world, train_info, val_info = prepare_world(train, validation, history, specification)
            moment_audits.append(val_info[3])
            macro_predictions.extend(
                release_predictions(world, history.at(row.forecast_timestamp), row.meeting_id)
            )
            for mode, C in selected.items():
                head = classifier(mode, C, features, config, specification)
                test_predictions.append(predict(train, validation, train_info, val_info, head))
                if index == 0 and mode == "wm_augmented":
                    head.synthetic.to_parquet(
                        out / "synthetic_latent_training_example.parquet", index=False
                    )
                    train_info[3].to_parquet(out / "synthetic_parent_audit.parquet", index=False)
            if index == 0:
                world.simulate(
                    history.at(row.forecast_timestamp), **specification["scenario"], seed=ev["seed"]
                ).to_parquet(out / "synthetic_monthly_paths.parquet", index=False)
            if (index + 1) % 5 == 0:
                print(
                    f"Test forecasts saved in memory: {index + 1}/{len(test)}; no model selection on test",
                    flush=True,
                )
    fresh = score(pd.concat(test_predictions, ignore_index=True))
    fresh.to_parquet(out / "world_predictions.parquet", index=False)
    pd.concat(moment_audits).to_parquet(out / "test_state_audit.parquet", index=False)
    releases = score_releases(macro_predictions, history)
    releases.to_parquet(out / "release_predictions.parquet", index=False)
    releases[releases.target_status == "scored"].groupby(["model_name", "channel"]).agg(
        n=("crps", "size"),
        crps=("crps", "mean"),
        standardized_crps=("standardized_crps", "mean"),
        negative_log_density=("negative_log_density", "mean"),
        coverage_90=("covered_90", "mean"),
    ).to_csv(out / "release_comparison.csv")
    baseline = pd.read_parquet(Path(specification["baseline_run"]) / "predictions.parquet")
    if set(baseline.meeting_id) != set(fresh.meeting_id):
        raise ValueError("Frozen baselines and world models must share test meetings")
    combined = pd.concat([baseline, fresh], ignore_index=True)
    combined.to_parquet(out / "predictions.parquet", index=False)
    summary(combined).to_csv(out / "model_comparison.csv", index=False)
    summary(combined, ("model_name", "actual_class")).to_csv(out / "by_class.csv", index=False)
    cut_diagnostics(combined).to_csv(out / "cut_diagnostics.csv", index=False)
    paired_differences(
        combined, ev["bootstrap_replicates"], ev["block_length_meetings"], ev["seed"]
    ).to_csv(out / "paired_differences.csv", index=False)
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
                "augmentation": "32 latent draws per real meeting, each weight 1/32; observed labels only",
                "limitations": [
                    "Two-stage Gaussian factor approximation",
                    "Parameter uncertainty is not integrated",
                    "No historical release-calendar reconstruction",
                    "Synthetic monthly paths are scenarios, not policy-labeled training examples",
                ],
            },
            indent=2,
        )
    )
    return out
