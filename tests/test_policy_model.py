"""Synthetic-only fixtures for the ordered Taylor-type reaction models."""

import numpy as np
import pandas as pd
import pytest

from rates_forecasting.evaluation.policy import select
from rates_forecasting.models.baselines import CLASSES
from rates_forecasting.models.policy import (
    INPUTS,
    OrderedFree,
    TaylorOrdered,
    ordered_loss,
    ordered_probabilities,
)

TRUE = np.array([-1.0, np.log(2.5), np.log(0.8), 0.5, 1.0, 0.6, -0.8])


def simulate(n, seed=0):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(
        {
            "core_cpi_yoy": rng.uniform(0.5, 5, n),
            "unemployment": rng.uniform(3.5, 9, n),
            "policy_midpoint": rng.choice([0.125, 1.0, 2.5, 4.0, 5.5], n),
            "previous_scheduled_bps": rng.choice([-50.0, -25.0, 0.0, 0.0, 25.0], n),
            "unemployment_3m_change": rng.normal(0, 0.4, n),
            "data_kind": "synthetic",
        }
    )
    z, _, _ = TaylorOrdered.pressure(TRUE, frame[INPUTS].to_numpy())
    p = ordered_probabilities(TRUE[0], TRUE[1], z, frame.policy_midpoint.to_numpy() <= 0.125)
    codes = (rng.uniform(size=n)[:, None] > p.cumsum(axis=1)).sum(axis=1)
    frame["target_class"] = np.asarray(CLASSES)[np.minimum(codes, 2)]
    return frame


def numeric_gradient(f, theta, step=1e-6):
    grad = np.zeros_like(theta)
    for k in range(len(theta)):
        e = np.zeros_like(theta)
        e[k] = step
        grad[k] = (f(theta + e)[0] - f(theta - e)[0]) / (2 * step)
    return grad


def test_analytic_gradients_match_finite_differences():
    frame = simulate(300, seed=1)
    X = frame[INPUTS].to_numpy()
    y = np.array([CLASSES.index(c) for c in frame.target_class])
    bound = frame.policy_midpoint.to_numpy() <= 0.125
    theta = TRUE + np.random.default_rng(2).normal(0, 0.2, 7)
    rule = TaylorOrdered(0.3)
    f = lambda t: rule.objective(t, X, y, bound)
    assert np.allclose(f(theta)[1], numeric_gradient(f, theta), rtol=1e-4, atol=1e-4)
    Xs = (X - X.mean(axis=0)) / X.std(axis=0)
    control = OrderedFree(0.5)
    g = lambda t: control.objective(t, Xs, y, bound)
    start = np.random.default_rng(3).normal(0, 0.3, 7)
    assert np.allclose(g(start)[1], numeric_gradient(g, start), rtol=1e-4, atol=1e-4)


def test_lower_bound_removes_cut_probability():
    frame = simulate(400, seed=4)
    for fitted in (TaylorOrdered(0.1).fit(frame), OrderedFree(1.0).fit(frame)):
        p = fitted.predict_proba(frame)
        bound = frame.policy_midpoint.to_numpy() <= 0.125
        assert bound.any() and (p[bound, 0] == 0).all() and (p[~bound, 0] > 0).all()
        assert np.allclose(p.sum(axis=1), 1)
    with pytest.raises(ValueError, match="lower bound"):
        ordered_loss(0.0, 0.0, np.zeros(1), np.array([0]), np.array([True]))


def test_recovers_known_rule_from_large_sample():
    fitted = TaylorOrdered(0.0).fit(simulate(6000, seed=5)).parameters()
    assert fitted["converged"]
    assert abs(fitted["a_pi"] - 0.5) < 0.2 and abs(fitted["a_u"] - 1.0) < 0.2
    assert abs(fitted["scale"] - 0.8) < 0.2 and abs(fitted["b_momentum"] - 0.6) < 0.3


def test_prior_strength_pulls_toward_its_own_centers():
    frame = simulate(60, seed=6)
    right = TaylorOrdered(10.0).fit(frame).parameters()
    wrong = TaylorOrdered(10.0, {"a_pi": -0.5, "a_u": -1.0}).fit(frame).parameters()
    assert abs(right["a_pi"] - 0.5) < 0.05 and abs(right["a_u"] - 1.0) < 0.05
    assert abs(wrong["a_pi"] + 0.5) < 0.05 and abs(wrong["a_u"] + 1.0) < 0.05


def test_higher_inflation_raises_hike_and_lowers_cut_probability():
    fitted = TaylorOrdered(0.1).fit(simulate(1500, seed=7))
    grid = pd.DataFrame(
        {
            "core_cpi_yoy": np.linspace(1, 5, 9),
            "unemployment": 5.0,
            "policy_midpoint": 2.5,
            "previous_scheduled_bps": 0.0,
            "unemployment_3m_change": 0.0,
        }
    )
    p = fitted.predict_proba(grid)
    assert (np.diff(p[:, 2]) > 0).all() and (np.diff(p[:, 0]) < 0).all()


def test_selection_breaks_ties_with_smaller_grid_value():
    table = pd.DataFrame(
        {
            "model_name": ["taylor_ordered"] * 3,
            "value": [0.3, 0.0, 0.1],
            "cut_weighted_brier": [0.5, 0.5, 0.6],
            "brier": [0.4, 0.4, 0.3],
        }
    )
    assert select(table) == {"taylor_ordered": 0.0}
