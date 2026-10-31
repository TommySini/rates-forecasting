"""Synthetic chronology and cost fixtures, never empirical benchmark observations."""

import copy
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest
import yaml

from rates_forecasting.evaluation.metrics import cut_diagnostics, score_rows
from rates_forecasting.evaluation.tuning import (
    candidates,
    cross_validate,
    development_folds,
    resolve_split,
)


@pytest.fixture
def tuning_config():
    with open("configs/cut_sensitive.yaml") as file:
        config = yaml.safe_load(file)
    config["evaluation"]["search"]["grids"] = {
        "frequency": {"alpha": [0.5, 1.0]},
        "logistic": {"C": [0.1, 1.0]},
        "trees": {
            "max_depth": [1, 2],
            "max_iter": [5],
            "learning_rate": [0.1],
            "min_samples_leaf": [10],
            "l2_regularization": [1.0],
        },
    }
    return config


@pytest.fixture
def fixture_panel():
    days = pd.date_range("2006-01-01", periods=159, freq="MS", tz="UTC")
    return pd.DataFrame(
        {
            "meeting_id": [f"SYNTHETIC-{i}" for i in range(159)],
            "forecast_timestamp": [day.to_pydatetime() - timedelta(days=7) for day in days],
            "decision_date": days.strftime("%Y-%m-%d"),
            "target_label_available_at": [day.to_pydatetime() + timedelta(days=1) for day in days],
            "target_class": np.resize(["cut", "hold", "hike"], 159),
            "x": np.arange(159) % 7,
            "data_kind": "synthetic",
        }
    )


def test_fraction_rounding_retains_each_meeting(fixture_panel, tuning_config):
    config, ledger, counts = resolve_split(fixture_panel, tuning_config)
    assert counts.n.tolist() == [119, 20, 20]
    assert len(ledger) == ledger.meeting_id.nunique() == 159
    assert config["sample"]["development_start"] == fixture_panel.iloc[119].decision_date
    assert config["sample"]["holdout_start"] == fixture_panel.iloc[139].decision_date
    assert "development_start" not in tuning_config["sample"]  # No mutation.


@pytest.mark.parametrize(
    "fractions",
    [
        {"training": 0.75, "development": 0.75, "test": 0.75},
        {"training": 0.75, "development": 0.25, "test": 0},
        {"training": 0.75, "development": 0.125, "test": np.nan},
    ],
)
def test_invalid_fraction_split_rejected(fixture_panel, tuning_config, fractions):
    tuning_config["sample"]["fractions"] = fractions
    with pytest.raises(ValueError, match="sum to one"):
        resolve_split(fixture_panel, tuning_config)


def test_split_rejects_duplicate_meetings(fixture_panel, tuning_config):
    duplicated = pd.concat([fixture_panel, fixture_panel.iloc[[0]]])
    with pytest.raises(ValueError, match="Duplicate"):
        resolve_split(duplicated, tuning_config)


def test_cv_label_availability_and_test_isolation(fixture_panel, tuning_config):
    config, ledger, _ = resolve_split(fixture_panel, tuning_config)
    # A previous event's label is delayed beyond the first validation issuance.
    fixture_panel.loc[118, "target_label_available_at"] = pd.Timestamp("2030-01-01T00:00Z")
    folds = list(development_folds(fixture_panel, config))
    validation_ids = []
    for _, train, validation in folds:
        assert (train.target_label_available_at < validation.forecast_timestamp.min()).all()
        assert (train.forecast_timestamp < validation.forecast_timestamp.min()).all()
        assert "SYNTHETIC-118" not in set(train.meeting_id)
        assert not set(train.meeting_id) & set(validation.meeting_id)
        validation_ids.extend(validation.meeting_id)
    assert set(validation_ids) == set(ledger.loc[ledger.split == "development", "meeting_id"])
    assert len(validation_ids) == len(set(validation_ids)) == 20


def test_search_cannot_use_test_labels_or_features(fixture_panel, tuning_config):
    config, _, _ = resolve_split(fixture_panel, tuning_config)
    original = cross_validate(fixture_panel, config, ["x"])
    mutated = fixture_panel.copy()
    mask = mutated.decision_date >= config["sample"]["holdout_start"]
    mutated.loc[mask, "x"] = 1e12
    mutated.loc[mask, "target_class"] = "UNKNOWN-FUTURE-CLASS"
    mutated.loc[mask, "target_label_available_at"] = pd.Timestamp("1990-01-01T00:00Z")
    changed = cross_validate(mutated, config, ["x"])
    assert original[0] == changed[0]
    for a, b in zip(original[1:], changed[1:]):
        pd.testing.assert_frame_equal(a, b)


def test_full_grid_is_bounded_and_covers_parameters(tuning_config):
    assert len(candidates(tuning_config)) == 6
    limited = copy.deepcopy(tuning_config)
    limited["evaluation"]["search"]["max_candidates"] = 5
    with pytest.raises(ValueError, match="budget"):
        candidates(limited)
    del tuning_config["evaluation"]["search"]["grids"]["trees"]["learning_rate"]
    with pytest.raises(ValueError, match="all supported"):
        candidates(tuning_config)


def test_cut_weighting_and_decision_cost_preserve_probabilities():
    frame = pd.DataFrame(
        {
            "model_name": ["fixture", "fixture"],
            "p_cut": [0.4, 0.4],
            "p_hold": [0.5, 0.5],
            "p_hike": [0.1, 0.1],
            "actual_class": ["cut", "hold"],
        }
    )
    scores = score_rows(frame, cut_weight=2, missed_cut_cost=2)
    np.testing.assert_allclose(scores.brier, [0.62, 0.42])
    np.testing.assert_allclose(scores.cut_weighted_brier, [0.98, 0.58])
    assert scores.predicted_class.tolist() == ["hold", "hold"]
    assert scores.cut_sensitive_class.tolist() == ["cut", "cut"]
    assert scores.correct.tolist() == [False, True]
    pd.testing.assert_frame_equal(scores[["p_cut", "p_hold", "p_hike"]], frame.iloc[:, 1:4])
    report = cut_diagnostics(scores).set_index("decision_rule")
    assert report.loc["argmax", "missed_cuts"] == 1
    assert report.loc["missed_cut_cost", "missed_cuts"] == 0
    assert report.loc["missed_cut_cost", "false_cut_calls"] == 1


def test_component_weighting_rewards_truthful_probabilities():
    truth = np.array([0.15, 0.70, 0.15])

    def expected_score(p):
        frame = pd.DataFrame(np.tile(p, (3, 1)), columns=["p_cut", "p_hold", "p_hike"])
        frame["actual_class"] = ["cut", "hold", "hike"]
        return score_rows(frame, cut_weight=2).cut_weighted_brier @ truth

    assert expected_score(truth) < expected_score([0.35, 0.50, 0.15])


def test_no_cuts_has_undefined_recall():
    frame = pd.DataFrame(
        {
            "model_name": ["fixture"],
            "p_cut": [0.1],
            "p_hold": [0.8],
            "p_hike": [0.1],
            "actual_class": ["hold"],
        }
    )
    result = cut_diagnostics(score_rows(frame))
    assert result.cut_recall.isna().all()
