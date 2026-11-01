"""Independent artifact checks. No model fitting, tuning, or network access."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from rates_forecasting.models.baselines import CLASSES, validate_probabilities
from rates_forecasting.models.world import MacroHistory
from rates_forecasting.paths import dataset_path


def verify(root):
    spec = json.loads((root / "specification.json").read_text())
    config = spec["base"]
    panel = pd.read_parquet(root / "input_panel.parquet")
    assert set(panel.data_kind) == {"empirical"}
    split = pd.read_csv(root / "split_meetings.csv")
    dev_ids = set(split.loc[split.split == "development", "meeting_id"])
    test_ids = set(split.loc[split.split == "test", "meeting_id"])
    assert len(test_ids) == 26 and len(panel) == 207
    predictions = pd.read_parquet(root / "predictions.parquet")
    assert set(predictions.meeting_id) == test_ids
    assert not predictions.duplicated(["model_name", "meeting_id"]).any()
    p = validate_probabilities(predictions[["p_cut", "p_hold", "p_hike"]].to_numpy())
    truth = panel.set_index("meeting_id").target_class
    assert predictions.actual_class.eq(predictions.meeting_id.map(truth)).all()
    y = np.array([CLASSES.index(x) for x in predictions.actual_class])
    np.testing.assert_allclose(((p - np.eye(3)[y]) ** 2).sum(axis=1), predictions.brier)
    np.testing.assert_allclose(
        -np.log(np.clip(p[np.arange(len(p)), y], 1e-15, 1)), predictions.log_loss
    )
    table = pd.read_csv(root / "model_comparison.csv").set_index("model_name")
    np.testing.assert_allclose(predictions.groupby("model_name").brier.mean(), table.brier)
    assert (
        pd.read_csv(root / "calibration.csv").groupby(["model_name", "class"]).n.sum().eq(26).all()
    )
    baseline = pd.read_parquet(Path(spec["baseline_run"]) / "predictions.parquet")
    saved = predictions[predictions.model_name.isin(baseline.model_name)][baseline.columns]
    pd.testing.assert_frame_equal(
        saved.reset_index(drop=True), baseline.reset_index(drop=True), check_dtype=False
    )
    observed = pd.read_parquet(dataset_path(config, "interim", "observations.parquet"))
    history = MacroHistory(observed)
    world = pd.read_parquet(root / "world_predictions.parquet")
    for row in world.itertuples():
        train = panel[
            (panel.forecast_timestamp < row.forecast_timestamp)
            & (panel.target_label_available_at < row.forecast_timestamp)
        ]
        assert row.training_n == len(train)
        assert row.training_cutoff == train.target_label_available_at.max()
        assert row.world_parameter_cutoff == train.forecast_timestamp.max()
        assert (
            row.world_parameter_max_available_at
            <= row.world_parameter_cutoff
            < row.forecast_timestamp
        )
        assert row.state_input_max_available_at <= row.forecast_timestamp
        assert row.total_training_weight == len(train)
        assert row.world_fit_months == len(history.at(row.world_parameter_cutoff).values.dropna())
    cv = pd.read_parquet(root / "cv_predictions.parquet")
    assert set(cv.meeting_id) == dev_ids and not set(cv.meeting_id) & test_ids
    assert not cv.duplicated(["model_name", "C", "meeting_id"]).any()
    assert cv.groupby(["model_name", "C"]).size().eq(len(dev_ids)).all()
    for fold, frame in cv.groupby("fold"):
        first = frame.forecast_timestamp.min()
        train = panel[
            (panel.forecast_timestamp < first) & (panel.target_label_available_at < first)
        ]
        assert frame.training_n.eq(len(train)).all()
        assert frame.total_training_weight.eq(len(train)).all()
        assert frame.world_parameter_cutoff.eq(train.forecast_timestamp.max()).all()
        assert (frame.world_parameter_max_available_at <= frame.world_parameter_cutoff).all()
        assert (frame.state_input_max_available_at <= frame.forecast_timestamp).all()
    selected = json.loads((root / "selected_models.json").read_text())
    for name, frame in pd.read_csv(root / "cv_candidates.csv").groupby("model_name"):
        assert selected[name] == frame.sort_values(["cut_weighted_brier", "brier", "C"]).iloc[0].C
    draws = pd.read_parquet(root / "synthetic_latent_training_example.parquet")
    assert set(draws.data_kind) == {"synthetic_latent_draw"}
    assert len(draws) == 32 * draws.parent_meeting_id.nunique()
    np.testing.assert_allclose(draws.groupby("parent_meeting_id").training_weight.sum(), 1)
    assert not set(draws.parent_meeting_id) & test_ids
    assert draws.observed_parent_class.eq(draws.parent_meeting_id.map(truth)).all()
    if (root / "synthetic_parent_audit.parquet").exists():
        parents = pd.read_parquet(root / "synthetic_parent_audit.parquet")
        assert set(parents.meeting_id) == set(draws.parent_meeting_id)
        assert (parents.state_input_max_available_at <= parents.forecast_timestamp).all()
    paths = pd.read_parquet(root / "synthetic_monthly_paths.parquet")
    assert set(paths.data_kind) == {"synthetic_scenario"} and "target_class" not in paths
    releases = pd.read_parquet(root / "release_predictions.parquet")
    released = releases[releases.target_status == "scored"]
    assert (released.target_available_at > released.forecast_timestamp).all()
    assert (released.parameter_cutoff < released.forecast_timestamp).all()
    actual_coverage = (
        (released.actual - released["mean"]).abs()
        <= 1.6448536269514722 * np.sqrt(released.variance)
    ).astype(float)
    np.testing.assert_array_equal(actual_coverage, released.covered_90.to_numpy(float))
    expected_coverage = (
        released.assign(coverage=actual_coverage).groupby(["model_name", "channel"]).coverage.mean()
    )
    stored = pd.read_csv(root / "release_comparison.csv").set_index(["model_name", "channel"])
    np.testing.assert_allclose(expected_coverage, stored.coverage_90)
    assert (root / "probabilities.png").stat().st_size > 10000
    assert (root / "calibration.png").stat().st_size > 10000
    result = {
        "status": "passed",
        "real_test_meetings": 26,
        "synthetic_test_meetings": 0,
        "checks": [
            "observed targets and recomputed probability scores",
            "unchanged frozen baselines",
            "training-only world parameters and preprocessing weights",
            "state inputs eligible at issuance",
            "chronological CV excludes test",
            "selected C matches development objective",
            "synthetic provenance and per-parent weight one",
            "release targets occur after forecast; interval coverage independently recomputed",
        ],
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    print(str(root), result["status"])


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/verify_world_model.py reports/world_model_runs/<fingerprint>"
        )
    verify(Path(sys.argv[1]))
