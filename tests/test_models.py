import numpy as np
import pandas as pd
import pytest

from rates_forecasting.evaluation.metrics import block_indices, score_rows
from rates_forecasting.evaluation.run import evaluate, training_rows
from rates_forecasting.models.baselines import Frequency, Supervised, validate_probabilities


def test_smoothed_frequency_has_no_zero_class():
    training = pd.DataFrame({"target_class": ["hold"] * 3})
    p = Frequency().fit(training).predict_proba(pd.DataFrame(index=range(2)))
    np.testing.assert_allclose(p[0], [1 / 6, 4 / 6, 1 / 6])


@pytest.mark.parametrize("p", [[[0, -1, 2]], [[0.1, 0.1, 0.1]], [[np.nan, 0, 1]], [[0.5, 0.5]]])
def test_invalid_probability_rejected(p):
    with pytest.raises(ValueError):
        validate_probabilities(p)


def test_preprocessing_fit_only_on_training(config):
    train = pd.DataFrame(
        {"x": [0.0, 2.0, np.nan, 4.0, 6.0, 8.0], "target_class": ["cut", "hold", "hike"] * 2}
    )
    m = Supervised("logistic", 1.0, config, ["x"]).fit(train)
    median = m.pipeline.named_steps["imputer"].statistics_.copy()
    scale = m.pipeline.named_steps["scale"].mean_.copy()
    m.predict_proba(pd.DataFrame({"x": [1e9]}))
    np.testing.assert_allclose(median, [4.0])
    np.testing.assert_allclose(m.pipeline.named_steps["scale"].mean_, scale)
    np.testing.assert_allclose(m.pipeline.named_steps["imputer"].statistics_, median)


def test_label_must_be_observed_before_fit():
    panel = pd.DataFrame(
        {
            "forecast_timestamp": pd.to_datetime(["2020-01-01T00:00Z"] * 2),
            "target_label_available_at": pd.to_datetime(["2020-01-02T00:00Z", "2020-02-02T00:00Z"]),
        }
    )
    assert training_rows(panel, pd.Timestamp("2020-02-01T00:00Z")).index.tolist() == [0]


def test_score_normalization_and_clipping():
    frame = pd.DataFrame(
        {
            "p_cut": [1.0, 0.0],
            "p_hold": [0.0, 1.0],
            "p_hike": [0.0, 0.0],
            "actual_class": ["cut", "cut"],
        }
    )
    scores = score_rows(frame)
    assert scores.brier.tolist() == [0.0, 2.0]
    assert np.isfinite(scores.log_loss).all()


def test_bootstrap_retains_local_sequences():
    ix = block_indices(20, 4, np.random.default_rng(1))
    assert len(ix) == 20
    for block in ix.reshape(-1, 4):
        np.testing.assert_array_equal(np.diff(block) % 20, [1, 1, 1])


def test_synthetic_run_cannot_be_presented_as_empirical(config, tmp_path):
    with pytest.raises(ValueError, match="Synthetic"):
        evaluate(pd.DataFrame({"data_kind": ["synthetic"]}), config, tmp_path)
