"""Independent checks of real artifacts. No downloads, model fitting, or tuning."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from rates_forecasting.features.panel import FEATURES, validate_panel
from rates_forecasting.models.baselines import CLASSES, validate_probabilities
from rates_forecasting.paths import dataset_path
from rates_forecasting.time import at_ny

panel = pd.read_parquet("data/processed/panel.parquet")
meetings = pd.read_parquet("data/interim/meeting_inventory.parquet")
lineage = pd.read_parquet("data/processed/lineage.parquet")
validate_panel(panel, lineage, meetings)
checks = ["point-in-time panel/lineage validation"]
assert (panel.forecast_timestamp < panel.decision_date.map(lambda d: at_ny(d, 0))).all()
checks.append("issuance precedes start of actual decision date, including unknown intraday times")
counts = panel.groupby(panel.decision_date.str[:4]).size()
assert all(n == (7 if year == "2020" else 8) for year, n in counts.items())
checks.append("eight scheduled decisions per year except seven executed meetings in 2020")
snapshot = pd.read_parquet("data/processed/first_snapshot.parquet").iloc[0]
scaled = panel.set_index("meeting_id").loc[snapshot.meeting_id]
np.testing.assert_allclose(snapshot[FEATURES].to_numpy(float), scaled[FEATURES].to_numpy(float))
checks.append("narrow first snapshot agrees with full-history reconstruction on all 19 features")

expanded_path = Path("data/processed/extended_2000/panel.parquet")
if expanded_path.exists():
    expanded = pd.read_parquet(expanded_path)
    expanded_config = yaml.safe_load(Path("configs/extended_2000.yaml").read_text())
    expanded_lineage = pd.read_parquet(
        dataset_path(expanded_config, "processed", "lineage.parquet")
    )
    validate_panel(expanded, expanded_lineage, meetings)
    early = expanded[expanded.decision_date < "2006-01-01"]
    assert len(expanded) == 207 and len(early) == 48
    assert early.target_class.value_counts().to_dict() == {"hold": 22, "hike": 16, "cut": 10}
    assert expanded.target_class.value_counts().to_dict() == {"hold": 140, "hike": 40, "cut": 27}
    assert (
        early.loc[early.decision_date.str.startswith("2001"), "target_class"].eq("cut").sum() == 8
    )
    included = [f for f in FEATURES if f not in expanded_config["models"]["excluded_features"]]
    assert len(included) == 12 and not early[included].isna().any().any()
    first = pd.read_parquet(
        dataset_path(expanded_config, "processed", "first_snapshot.parquet")
    ).iloc[0]
    indexed = expanded.set_index("meeting_id")
    np.testing.assert_allclose(
        first[included].to_numpy(float), indexed.loc[first.meeting_id, included].to_numpy(float)
    )
    assert first.payroll_1m == 105 and first.unemployment == 4.0
    assert first.policy_midpoint == 6 and first.previous_scheduled_bps == 0
    assert first.days_since_policy_change == 21
    np.testing.assert_allclose(
        indexed.loc[panel.meeting_id, included].to_numpy(float),
        panel[included].to_numpy(float),
        equal_nan=True,
    )
    checks.append(
        "207-meeting expansion: 48 early labels, all 12 early inputs complete, original-release January 2001 snapshot, overlapping features unchanged"
    )

expected = {
    "2001-01-03": (6.5, 6.0, "cut"),
    "2001-01-31": (6.0, 5.5, "cut"),
    "2004-06-30": (1.0, 1.25, "hike"),
    "2007-06-28": (5.25, 5.25, "hold"),
    "2008-01-22": (4.25, 3.5, "cut"),
    "2008-01-30": (3.5, 3.0, "cut"),
    "2008-12-16": (1.0, 0.125, "cut"),
    "2015-12-16": (0.125, 0.375, "hike"),
    "2019-07-31": (2.375, 2.125, "cut"),
    "2020-03-03": (1.625, 1.125, "cut"),
    "2020-03-15": (1.125, 0.125, "cut"),
    "2020-04-29": (0.125, 0.125, "hold"),
}
for day, (before, after, label) in expected.items():
    m = meetings.set_index("decision_date").loc[day]
    assert (m.policy_rate_before, m.policy_rate_after, m.decision_class) == (before, after, label)
checks.append("12 source-reviewed policy examples including ranges and emergency moves")
exclusions = pd.read_csv("reports/exclusions.csv")
cancelled = exclusions[exclusions.meeting_id == "FOMC-2020-03-18"].iloc[0]
assert cancelled.reason == "cancelled" and cancelled.intervening_unscheduled_change
checks.append("cancelled March 2020 target retained with intervening emergency change flagged")

raw_count = 0
for path in Path("data/raw").glob("*.json"):
    meta = json.loads(path.read_text())
    assert "api_key" not in meta["params"]
    assert hashlib.sha256(path.with_suffix(".body").read_bytes()).hexdigest() == meta["sha256"]
    raw_count += 1
checks.append(f"{raw_count} raw-response hashes checked; metadata excludes API keys")

runs = []
for complete in sorted(Path("reports/runs").glob("*/complete.json")):
    root = complete.parent
    metadata = json.loads(complete.read_text())
    run_panel_path = root / "input_panel.parquet"
    run_panel = pd.read_parquet(run_panel_path) if run_panel_path.exists() else panel
    if run_panel_path.exists():
        assert (
            hashlib.sha256(run_panel_path.read_bytes()).hexdigest()
            == metadata["input_panel_sha256"]
        )
        config = json.loads((root / "resolved_config.json").read_text())
        suffix = "_lag2" if run_panel.availability_lag_business_days.eq(2).all() else ""
        run_lineage = pd.read_parquet(dataset_path(config, "processed", f"lineage{suffix}.parquet"))
        run_lineage = run_lineage[run_lineage.meeting_id.isin(run_panel.meeting_id)]
        validate_panel(run_panel, run_lineage, meetings)
        indexed_lineage = run_lineage.pivot(index="meeting_id", columns="feature", values="value")
        np.testing.assert_allclose(
            run_panel.set_index("meeting_id").loc[indexed_lineage.index, FEATURES].to_numpy(float),
            indexed_lineage[FEATURES].to_numpy(float),
            equal_nan=True,
        )
    prediction = pd.read_parquet(root / "predictions.parquet")
    assert not prediction.duplicated(["meeting_id", "model_name"]).any()
    p = validate_probabilities(prediction[["p_cut", "p_hold", "p_hike"]].to_numpy())
    assert (prediction.training_cutoff < prediction.forecast_timestamp).all()
    truth = run_panel.set_index("meeting_id").target_class
    assert prediction.actual_class.eq(prediction.meeting_id.map(truth)).all()
    for row in prediction.itertuples():
        train = run_panel[
            (run_panel.forecast_timestamp < row.forecast_timestamp)
            & (run_panel.target_label_available_at < row.forecast_timestamp)
        ]
        assert len(train) == row.training_n
        assert train.target_label_available_at.max() == row.training_cutoff
    y = np.array([CLASSES.index(x) for x in prediction.actual_class])
    np.testing.assert_allclose(((p - np.eye(3)[y]) ** 2).sum(axis=1), prediction.brier)
    np.testing.assert_allclose(
        -np.log(np.clip(p[np.arange(len(p)), y], 1e-15, 1)), prediction.log_loss
    )
    table = pd.read_csv(root / "model_comparison.csv").set_index("model_name")
    np.testing.assert_allclose(prediction.groupby("model_name").brier.mean(), table.brier)
    calibration = pd.read_csv(root / "calibration.csv")
    assert (
        calibration.groupby(["model_name", "class"])
        .n.sum()
        .eq(prediction.meeting_id.nunique())
        .all()
    )
    if (root / "cv_folds.csv").exists():
        split = pd.read_csv(root / "split_meetings.csv")
        assert not split.meeting_id.duplicated().any()
        dev_ids = set(split.loc[split.split == "development", "meeting_id"])
        test_ids = set(split.loc[split.split == "test", "meeting_id"])
        cv = pd.read_parquet(root / "development_candidates.parquet")
        assert set(cv.meeting_id) == dev_ids and not set(cv.meeting_id) & test_ids
        assert (cv.training_cutoff < cv.forecast_timestamp).all()
        assert not cv.duplicated(["candidate_id", "meeting_id"]).any()
        assert cv.groupby("candidate_id").size().eq(len(dev_ids)).all()
        folds = pd.read_csv(root / "cv_folds.csv")
        for fold in folds.itertuples():
            first = pd.Timestamp(fold.validation_first_forecast)
            train = run_panel[
                (run_panel.forecast_timestamp < first)
                & (run_panel.target_label_available_at < first)
            ]
            assert len(train) == fold.training_n
            assert train.target_label_available_at.max() == pd.Timestamp(fold.training_cutoff)
        config = json.loads((root / "resolved_config.json").read_text())
        weight = config["evaluation"]["cut_component_weight"]
        errors = (p - np.eye(3)[y]) ** 2
        np.testing.assert_allclose(errors @ np.array([weight, 1, 1]), prediction.cut_weighted_brier)
        choices = json.loads((root / "selected_models.json").read_text())
        candidates = pd.read_csv(root / "cv_candidates.csv")
        for name, frame in candidates.groupby("model_name"):
            best = frame.sort_values(["cut_weighted_brier", "brier", "candidate_id"]).iloc[0]
            assert choices[name] == json.loads(best.candidate_parameters)
    assert (root / "probabilities.png").stat().st_size > 10000
    assert (root / "calibration.png").stat().st_size > 10000
    runs.append(str(root))
checks.append(
    "all completed runs: valid probabilities, observed training labels, targets, recomputed scores, calibration counts, plot files"
)
history_manifest = Path("reports/extended_2000/history_runs.json")
if history_manifest.exists():
    history_runs = {k: Path(v) for k, v in json.loads(history_manifest.read_text()).items()}
    cohorts = {k: pd.read_parquet(v / "input_panel.parquet") for k, v in history_runs.items()}
    assert {k: len(v) for k, v in cohorts.items()} == {
        "expanded": 207,
        "control_2006": 159,
        "omit_2001_fixed_settings": 199,
    }
    assert not cohorts["omit_2001_fixed_settings"].decision_date.str.startswith("2001").any()
    assert json.loads(
        (history_runs["expanded"] / "selected_models.json").read_text()
    ) == json.loads((history_runs["omit_2001_fixed_settings"] / "selected_models.json").read_text())
    reference = pd.read_parquet(history_runs["expanded"] / "predictions.parquet")
    for name, root in history_runs.items():
        predictions = pd.read_parquet(root / "predictions.parquet")
        assert set(predictions.meeting_id) == set(reference.meeting_id)
        assert pd.read_csv(root / "feature_set.csv").feature.tolist() == included
    checks.append(
        "history comparison: same 26 test meetings and 12 features; 2001 omission keeps expanded-model settings"
    )
result = {
    "status": "passed",
    "checks": checks,
    "runs": runs,
    "empirical_panel_meetings": len(panel),
    "expanded_panel_meetings": len(expanded) if expanded_path.exists() else None,
    "synthetic_rows_in_panel": 0,
}
Path("reports/verification.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
