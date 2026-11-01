"""Synthetic-only fixtures for world-model leakage and augmentation accounting."""

from datetime import timedelta
from math import pi, sqrt

import numpy as np
import pandas as pd
import pytest

from rates_forecasting.evaluation.world import gaussian_crps, release_predictions, score_releases
from rates_forecasting.models.world import (
    SERIES,
    LinearWorld,
    MacroHistory,
    WorldClassifier,
    posterior_draws,
)


@pytest.fixture
def macro_history():
    rng = np.random.default_rng(17)
    periods = pd.period_range("2000-01", periods=84, freq="M")
    signal = np.zeros(84)
    for t in range(1, 84):
        signal[t] = 0.7 * signal[t - 1] + rng.normal()
    levels = np.column_stack(
        [
            100 + np.cumsum(0.2 + 0.05 * signal + rng.normal(0, 0.02, 84)),
            100 + np.cumsum(0.15 + 0.03 * signal + rng.normal(0, 0.02, 84)),
            100000 + np.cumsum(100 + 30 * signal + rng.normal(0, 10, 84)),
            5 + 0.2 * signal + rng.normal(0, 0.1, 84),
            100 + np.cumsum(0.1 + 0.1 * signal + rng.normal(0, 0.05, 84)),
        ]
    )
    rows = []
    for t, period in enumerate(periods):
        available = (period + 1).start_time.to_pydatetime() + timedelta(days=5)
        for j, sid in enumerate(SERIES):
            rows.append(
                {
                    "series_id": sid,
                    "observation_period": period.start_time.date().isoformat(),
                    "vintage_start": available.date().isoformat(),
                    "value": levels[t, j],
                    "available_at": pd.Timestamp(available, tz="UTC"),
                    "data_kind": "synthetic",
                }
            )
    return MacroHistory(pd.DataFrame(rows))


def test_world_fit_cannot_use_future_revisions(macro_history):
    cutoff = pd.Timestamp("2005-12-20T23:00Z")
    original = LinearWorld().fit(macro_history.at(cutoff))
    changed = macro_history.observations.copy()
    changed.loc[changed.available_at > cutoff, "value"] = 1e9
    revision = changed.iloc[[0]].copy()
    revision["available_at"] = pd.Timestamp("2010-01-01T00:00Z")
    revision["vintage_start"] = "2010-01-01"
    revision["value"] = -1e9
    other = LinearWorld().fit(MacroHistory(pd.concat([changed, revision])).at(cutoff))
    for attribute in ("center", "scale", "H", "F", "Q", "R"):
        np.testing.assert_array_equal(getattr(original, attribute), getattr(other, attribute))
    assert original.max_fit_available_at <= original.fit_cutoff


def test_reference_month_does_not_imply_availability(macro_history):
    snapshot = macro_history.at(pd.Timestamp("2005-12-20T23:00Z"))
    assert snapshot.values.loc["2005-12"].isna().all()
    assert snapshot.values.loc["2005-11"].notna().all()
    with pytest.raises(ValueError, match="timezone"):
        macro_history.at("2005-12-20")


def test_filter_and_scenarios_are_finite_and_do_not_refit(macro_history):
    world = LinearWorld().fit(macro_history.at(pd.Timestamp("2005-12-20T23:00Z")))
    before = world.F.copy()
    snapshot = macro_history.at(pd.Timestamp("2006-02-20T23:00Z"))
    mean, cov = world.moments(snapshot)
    assert np.isfinite(mean).all() and np.linalg.eigvalsh(cov).min() > 0
    assert np.abs(np.linalg.eigvals(world.F)).max() <= 0.98 + 1e-10
    scenarios = world.simulate(snapshot, draws=8, steps=2, seed=4)
    assert len(scenarios) == 16 and set(scenarios.data_kind) == {"synthetic_scenario"}
    assert "target_class" not in scenarios
    np.testing.assert_array_equal(world.F, before)


def test_antithetic_draws_preserve_parent_mean_and_identity():
    means = np.array([[1.0, 2.0], [3.0, 4.0]])
    covs = np.array([np.eye(2), 2 * np.eye(2)])
    a = posterior_draws(means, covs, ["A", "B"], 32, 7)
    b = posterior_draws(means[::-1], covs[::-1], ["B", "A"], 32, 7)
    np.testing.assert_allclose(a.mean(axis=1), means, atol=1e-14)
    np.testing.assert_array_equal(a, b[::-1])


def test_augmentation_has_one_unit_of_weight_per_real_meeting():
    frame = pd.DataFrame(
        {
            "meeting_id": [f"SYNTHETIC-{i}" for i in range(30)],
            "x": np.arange(30) % 7,
            "target_class": ["cut", "hold", "hike"] * 10,
        }
    )
    means = np.column_stack([np.sin(np.arange(30)), np.cos(np.arange(30))])
    covs = np.zeros((30, 2, 2))
    augmented = WorldClassifier("wm_augmented", 0.1, ["x"], 3).fit(frame, means, covs)
    plain = WorldClassifier("wm_mean", 0.1, ["x"], 3).fit(frame, means, covs)
    assert augmented.total_training_weight == len(frame)
    np.testing.assert_allclose(
        augmented.synthetic.groupby("parent_meeting_id").training_weight.sum(), 1
    )
    assert set(augmented.synthetic.data_kind) == {"synthetic_latent_draw"}
    assert set(augmented.synthetic.parent_meeting_id) == set(frame.meeting_id)
    np.testing.assert_allclose(
        augmented.predict_proba(frame, means, covs),
        plain.predict_proba(frame, means, covs),
        atol=1e-6,
    )
    p = augmented.predict_proba(frame, means, covs)
    modified = frame.assign(target_class="UNOBSERVED-FUTURE-LABEL")
    np.testing.assert_array_equal(p, augmented.predict_proba(modified, means, covs))


def test_release_targets_are_separate_and_crps_is_normalized(macro_history):
    fit = macro_history.at(pd.Timestamp("2005-12-20T23:00Z"))
    world = LinearWorld().fit(fit)
    snapshot = macro_history.at(pd.Timestamp("2006-02-20T23:00Z"))
    predictions = release_predictions(world, snapshot, "SYNTHETIC-FOMC")
    assert len(predictions) == 10 and all("actual" not in x for x in predictions)
    actuals = score_releases(predictions, macro_history)
    assert actuals.target_status.eq("scored").all()
    assert (actuals.target_available_at > actuals.forecast_timestamp).all()
    assert actuals.crps.ge(0).all()
    assert gaussian_crps(0, 0, 1) == pytest.approx((sqrt(2) - 1) / sqrt(pi))
    unavailable = dict(predictions[0], target_period="2030-01")
    mixed = score_releases(predictions * 5 + [unavailable], macro_history)
    scored = mixed[mixed.target_status == "scored"]
    assert mixed.covered_90.dtype.kind == "f"
    grouped = scored.groupby(["model_name", "channel"]).covered_90.mean()
    expected = scored.groupby(["model_name", "channel"]).covered_90.apply(
        lambda values: np.asarray(values, dtype=float).mean()
    )
    np.testing.assert_allclose(grouped, expected)
