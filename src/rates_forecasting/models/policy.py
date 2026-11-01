"""Small ordered reaction models: a Taylor-type rule with explicit priors and controls.

Probabilities stay in cut/hold/hike order. At the effective lower bound a cut is
impossible and its probability mass belongs to hold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from rates_forecasting.models.baselines import CLASSES, validate_probabilities

INPUTS = [
    "core_cpi_yoy",
    "unemployment",
    "policy_midpoint",
    "previous_scheduled_bps",
    "unemployment_3m_change",
]
LOWER_BOUND_MIDPOINT = 0.125
NEUTRAL_REAL_RATE = 2.0
INFLATION_TARGET = 2.0
UNEMPLOYMENT_BENCHMARK = 5.0
TAYLOR_NAMES = [
    "tau_cut",
    "log_tau_gap",
    "log_scale",
    "a_pi",
    "a_u",
    "b_momentum",
    "b_unemployment_change",
]


def at_lower_bound(frame):
    return frame.policy_midpoint.to_numpy(dtype=float) <= LOWER_BOUND_MIDPOINT + 1e-9


def class_codes(frame):
    if not frame.target_class.isin(CLASSES).all():
        raise ValueError("Unknown target class")
    return np.array([CLASSES.index(x) for x in frame.target_class])


def ordered_probabilities(tau_cut, log_gap, z, lower_bound):
    tau_hike = tau_cut + np.exp(log_gap)
    cut = np.where(lower_bound, 0.0, expit(tau_cut - z))
    below_hike = expit(tau_hike - z)
    p = np.column_stack([cut, below_hike - cut, expit(z - tau_hike)])
    return validate_probabilities(np.clip(p, 0, 1) / np.clip(p, 0, 1).sum(axis=1, keepdims=True))


def ordered_loss(tau_cut, log_gap, z, y, lower_bound):
    """Negative log likelihood and its derivatives for tau_cut, log_gap and each z."""
    if (lower_bound & (y == 0)).any():
        raise ValueError("A cut cannot be observed at the effective lower bound")
    gap = np.exp(log_gap)
    fa = np.where(lower_bound, 0.0, expit(tau_cut - z))
    fb = expit(tau_cut + gap - z)
    upper = expit(z - tau_cut - gap)
    p = np.maximum(np.choose(y, [fa, fb - fa, upper]), 1e-12)
    # Derivatives of log p with respect to A = tau_cut - z and B = tau_hike - z.
    da = np.select([y == 0, y == 1], [1 - fa, -fa * (1 - fa) / p], 0.0)
    db = np.select([y == 1, y == 2], [fb * (1 - fb) / p, -fb], 0.0)
    return -np.log(p).sum(), -(da + db).sum(), -(db * gap).sum(), da + db


class TaylorOrdered:
    """Seven-parameter ordered rule; prior precision on a_pi/a_u scales with lambda * N."""

    def __init__(self, strength=0.0, centers=None, prior_sd=0.5):
        if not np.isfinite(strength) or strength < 0:
            raise ValueError("Prior strength must be finite and nonnegative")
        self.strength = strength
        self.centers = centers or {"a_pi": 0.5, "a_u": 1.0}
        self.prior_sd = prior_sd
        self.weak_mean = np.array(
            [0.0, np.log(2.0), 0.0, self.centers["a_pi"], self.centers["a_u"], 0.0, 0.0]
        )
        self.weak_sd = np.array([10.0, 2.0, 2.0, 5.0, 5.0, 2.0, 2.0])

    @staticmethod
    def pressure(theta, X):
        pi, u, i, previous, du = X.T
        scale = np.exp(theta[2])
        rule = (
            NEUTRAL_REAL_RATE
            + pi
            + theta[3] * (pi - INFLATION_TARGET)
            - theta[4] * (u - UNEMPLOYMENT_BENCHMARK)
        )
        gap = rule - i
        z = scale * gap + theta[5] * previous / 25 + theta[6] * du
        dz = np.column_stack(
            [
                scale * gap,
                scale * (pi - INFLATION_TARGET),
                -scale * (u - UNEMPLOYMENT_BENCHMARK),
                previous / 25,
                du,
            ]
        )
        return z, dz, gap

    def objective(self, theta, X, y, lower_bound):
        z, dz, _ = self.pressure(theta, X)
        loss, d_tau, d_gap, d_z = ordered_loss(theta[0], theta[1], z, y, lower_bound)
        grad = np.concatenate([[d_tau, d_gap], dz.T @ d_z])
        weak = (theta - self.weak_mean) / self.weak_sd
        loss += 0.5 * weak @ weak
        grad += weak / self.weak_sd
        precision = self.strength * len(y) / self.prior_sd**2
        for k, name in [(3, "a_pi"), (4, "a_u")]:
            loss += 0.5 * precision * (theta[k] - self.centers[name]) ** 2
            grad[k] += precision * (theta[k] - self.centers[name])
        return loss, grad

    def fit(self, training_data):
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        X = self.imputer.fit_transform(training_data[INPUTS])
        y, lower_bound = class_codes(training_data), at_lower_bound(training_data)
        start = self.weak_mean.copy()
        result = minimize(
            self.objective, start, args=(X, y, lower_bound), jac=True, method="L-BFGS-B"
        )
        if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
            raise RuntimeError(f"Ordered rule fit failed: {result.message}")
        self.theta, self.converged = result.x, bool(result.success)
        return self

    def parameters(self):
        t = self.theta
        return {
            "tau_cut": t[0],
            "tau_hike": t[0] + np.exp(t[1]),
            "scale": np.exp(t[2]),
            "a_pi": t[3],
            "a_u": t[4],
            "b_momentum": t[5],
            "b_unemployment_change": t[6],
            "converged": self.converged,
        }

    def predict_proba(self, forecast_data):
        X = self.imputer.transform(forecast_data[INPUTS])
        z, _, _ = self.pressure(self.theta, X)
        return ordered_probabilities(self.theta[0], self.theta[1], z, at_lower_bound(forecast_data))

    def gap(self, forecast_data):
        return self.pressure(self.theta, self.imputer.transform(forecast_data[INPUTS]))[2]


class OrderedFree:
    """Control: same inputs and ordered outcome, free ridge coefficients, no economics."""

    def __init__(self, C=1.0):
        if not np.isfinite(C) or C <= 0:
            raise ValueError("Positive C required")
        self.C = C

    def objective(self, theta, X, y, lower_bound):
        z = X @ theta[2:]
        loss, d_tau, d_gap, d_z = ordered_loss(theta[0], theta[1], z, y, lower_bound)
        grad = np.concatenate([[d_tau, d_gap], X.T @ d_z])
        weak = (theta[:2] - [0.0, np.log(2.0)]) / [10.0, 2.0]
        loss += 0.5 * weak @ weak + 0.5 * theta[2:] @ theta[2:] / self.C
        grad[:2] += weak / [10.0, 2.0]
        grad[2:] += theta[2:] / self.C
        return loss, grad

    def fit(self, training_data):
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        self.scaler = StandardScaler()
        X = self.scaler.fit_transform(self.imputer.fit_transform(training_data[INPUTS]))
        y, lower_bound = class_codes(training_data), at_lower_bound(training_data)
        start = np.concatenate([[0.0, np.log(2.0)], np.zeros(X.shape[1])])
        result = minimize(
            self.objective, start, args=(X, y, lower_bound), jac=True, method="L-BFGS-B"
        )
        if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
            raise RuntimeError(f"Ordered control fit failed: {result.message}")
        self.theta, self.converged = result.x, bool(result.success)
        return self

    def predict_proba(self, forecast_data):
        X = self.scaler.transform(self.imputer.transform(forecast_data[INPUTS]))
        z = X @ self.theta[2:]
        return ordered_probabilities(self.theta[0], self.theta[1], z, at_lower_bound(forecast_data))


DERIVED = {
    "previous_move": lambda d: d.previous_scheduled_bps / 25,
    "bill_1m_spread": lambda d: d.yield_1m - d.policy_midpoint,
    "bill_spread": lambda d: d.yield_3m - d.policy_midpoint,
    "two_year_spread": lambda d: d.yield_2y - d.policy_midpoint,
}


class WeakOrdered:
    """Untuned ordered model on a few interpretable inputs with weak N(0, 2^2) weights."""

    def __init__(self, inputs, coefficient_sd=2.0):
        if not inputs or any(name not in DERIVED for name in inputs):
            raise ValueError("Unknown ordered-model input")
        self.inputs, self.coefficient_sd = list(inputs), coefficient_sd

    def design(self, frame):
        return pd.DataFrame({name: DERIVED[name](frame) for name in self.inputs})

    def objective(self, theta, X, y, lower_bound):
        z = X @ theta[2:]
        loss, d_tau, d_gap, d_z = ordered_loss(theta[0], theta[1], z, y, lower_bound)
        mean = np.r_[0.0, np.log(2.0), np.zeros(X.shape[1])]
        sd = np.r_[10.0, 2.0, np.full(X.shape[1], self.coefficient_sd)]
        weak = (theta - mean) / sd
        grad = np.concatenate([[d_tau, d_gap], X.T @ d_z]) + weak / sd
        return loss + 0.5 * weak @ weak, grad

    def fit(self, training_data):
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        X = self.imputer.fit_transform(self.design(training_data))
        y, lower_bound = class_codes(training_data), at_lower_bound(training_data)
        start = np.r_[0.0, np.log(2.0), np.zeros(X.shape[1])]
        result = minimize(
            self.objective, start, args=(X, y, lower_bound), jac=True, method="L-BFGS-B"
        )
        if not np.isfinite(result.fun) or not np.isfinite(result.x).all():
            raise RuntimeError(f"Ordered model fit failed: {result.message}")
        self.theta, self.converged = result.x, bool(result.success)
        return self

    def parameters(self):
        t = self.theta
        return {
            "tau_cut": t[0],
            "tau_hike": t[0] + np.exp(t[1]),
            **{f"b_{name}": value for name, value in zip(self.inputs, t[2:])},
            "converged": self.converged,
        }

    def predict_proba(self, forecast_data):
        X = self.imputer.transform(self.design(forecast_data))
        z = X @ self.theta[2:]
        return ordered_probabilities(self.theta[0], self.theta[1], z, at_lower_bound(forecast_data))
