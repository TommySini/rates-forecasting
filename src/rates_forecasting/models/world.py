"""Small Gaussian economic world model and explicitly weighted latent augmentation.

This is an exploratory two-stage factor estimator, not a neural simulator or a
causally identified model. All economic histories are reconstructed as of cutoff.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from rates_forecasting.features.panel import asof_observations
from rates_forecasting.models.baselines import CLASSES, validate_probabilities
from rates_forecasting.time import NY

CHANNELS = ["cpi_mom", "core_cpi_mom", "payroll_change", "unemployment", "ip_mom"]
SERIES = ["CPIAUCSL", "CPILFESL", "PAYEMS", "UNRATE", "INDPRO"]


@dataclass
class MacroSnapshot:
    values: pd.DataFrame
    cutoff: pd.Timestamp
    max_available_at: pd.Timestamp
    eligible_versions: int


class MacroHistory:
    def __init__(self, observations):
        self.observations = observations[observations.series_id.isin(SERIES)].copy()
        self.cache = {}

    def at(self, cutoff):
        cutoff = pd.Timestamp(cutoff)
        if cutoff.tzinfo is None:
            raise ValueError("Macro cutoff must have a timezone")
        key = cutoff.isoformat()
        if key not in self.cache:
            observations = asof_observations(self.observations, cutoff)
            if observations.empty:
                raise ValueError("No eligible macro history")
            levels = observations.pivot(
                index="observation_period", columns="series_id", values="value"
            )
            levels.index = pd.PeriodIndex(levels.index, freq="M")
            final = pd.Period(cutoff.tz_convert(NY).date(), freq="M")
            levels = levels.reindex(pd.period_range(levels.index.min(), final, freq="M"))
            levels = levels.reindex(columns=SERIES)
            values = pd.DataFrame(index=levels.index)
            # Missing months remain missing. Never fill from a future observation.
            values["cpi_mom"] = 100 * levels.CPIAUCSL.pct_change(fill_method=None)
            values["core_cpi_mom"] = 100 * levels.CPILFESL.pct_change(fill_method=None)
            values["payroll_change"] = levels.PAYEMS.diff()
            values["unemployment"] = levels.UNRATE
            values["ip_mom"] = 100 * levels.INDPRO.pct_change(fill_method=None)
            self.cache[key] = MacroSnapshot(
                values, cutoff, observations.available_at.max(), len(observations)
            )
        return self.cache[key]


def positive_covariance(matrix, floor=1e-8):
    values, vectors = np.linalg.eigh((matrix + matrix.T) / 2)
    return (vectors * np.maximum(values, floor)) @ vectors.T


class LinearWorld:
    """PCA loadings + shrinkage VAR(1), Gaussian measurement model, Kalman filter."""

    def __init__(self, latent_dim=2, ridge=1.0, measurement_floor=0.05, stability=0.98):
        self.d = latent_dim
        self.ridge = ridge
        self.measurement_floor = measurement_floor
        self.stability = stability

    def fit(self, snapshot):
        complete = snapshot.values.dropna()
        if len(complete) < 36:
            raise ValueError("World model needs at least 36 complete past months")
        self.fit_cutoff = snapshot.cutoff
        self.max_fit_available_at = snapshot.max_available_at
        self.fit_months = len(complete)
        self.center = complete.mean().to_numpy()
        self.scale = complete.std(ddof=1).to_numpy()
        if (self.scale <= 0).any():
            raise ValueError("Constant macro training channel")
        y = (complete.to_numpy() - self.center) / self.scale
        _, _, vt = np.linalg.svd(y, full_matrices=False)
        self.H = vt[: self.d].T
        factors = y @ self.H
        adjacent = np.diff(complete.index.asi8) == 1
        previous, following = factors[:-1][adjacent], factors[1:][adjacent]
        if len(previous) < 24:
            raise ValueError("Insufficient consecutive macro transitions")
        self.F = np.linalg.solve(
            previous.T @ previous + self.ridge * np.eye(self.d), previous.T @ following
        ).T
        radius = np.abs(np.linalg.eigvals(self.F)).max()
        if radius > self.stability:
            self.F *= self.stability / radius
        residual = following - previous @ self.F.T
        self.Q = positive_covariance(np.cov(residual, rowvar=False), floor=1e-4)
        measurement = y - factors @ self.H.T
        self.R = np.maximum(measurement.var(axis=0, ddof=1), self.measurement_floor)
        # Stationary state covariance; the transition is explicitly stable.
        self.prior_cov = positive_covariance(
            np.linalg.solve(
                np.eye(self.d**2) - np.kron(self.F, self.F), self.Q.reshape(-1)
            ).reshape(self.d, self.d)
        )
        self.training_standardized = y
        self.training_periods = complete.index
        return self

    def filter(self, snapshot):
        mean, cov = np.zeros(self.d), self.prior_cov.copy()
        values = (snapshot.values.to_numpy() - self.center) / self.scale
        means, covariances = [], []
        for y in values:
            mean = self.F @ mean
            cov = self.F @ cov @ self.F.T + self.Q
            known = np.isfinite(y)
            if known.any():
                h, r = self.H[known], np.diag(self.R[known])
                gain = np.linalg.solve(h @ cov @ h.T + r, h @ cov).T
                mean = mean + gain @ (y[known] - h @ mean)
                residual = np.eye(self.d) - gain @ h
                cov = residual @ cov @ residual.T + gain @ r @ gain.T
            cov = (cov + cov.T) / 2
            means.append(mean.copy())
            covariances.append(cov.copy())
        return np.asarray(means), np.asarray(covariances)

    def moments(self, snapshot):
        means, covariances = self.filter(snapshot)
        return means[-1], positive_covariance(covariances[-1])

    def simulate(self, snapshot, draws=256, steps=3, seed=0):
        """Monthly economic scenarios, with no invented publication dates or Fed labels."""
        mean, cov = self.moments(snapshot)
        rng = np.random.default_rng(seed)
        state = rng.multivariate_normal(mean, cov, draws)
        result = []
        for step in range(1, steps + 1):
            state = state @ self.F.T + rng.multivariate_normal(np.zeros(self.d), self.Q, draws)
            y = state @ self.H.T + rng.normal(size=(draws, len(CHANNELS))) * np.sqrt(self.R)
            frame = pd.DataFrame(y * self.scale + self.center, columns=CHANNELS)
            frame["path_id"], frame["step"] = np.arange(draws), step
            frame["data_kind"] = "synthetic_scenario"
            frame["conditional_on"] = snapshot.cutoff.isoformat()
            result.append(frame)
        return pd.concat(result, ignore_index=True)


def posterior_draws(means, covariances, ids, draws, seed):
    if draws < 2 or draws % 2:
        raise ValueError("Use an even number of antithetic draws")
    result = []
    for mean, cov, meeting_id in zip(means, covariances, ids):
        key = int(hashlib.sha256(str(meeting_id).encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(np.random.SeedSequence([seed, key]))
        e = rng.normal(size=(draws // 2, len(mean)))
        e = np.concatenate([e, -e])
        root = np.linalg.cholesky(positive_covariance(cov))
        result.append(mean + e @ root.T)
    return np.asarray(result)


class WorldClassifier:
    def __init__(
        self, mode, C, features, seed, train_draws=32, prediction_draws=256, noise_scale=0.1
    ):
        self.mode, self.C, self.features, self.seed = mode, C, features, seed
        self.train_draws, self.prediction_draws = train_draws, prediction_draws
        self.noise_scale = noise_scale

    def fit(self, training, means, covariances, lags=None):
        self.imputer = SimpleImputer(
            strategy="median", add_indicator=True, keep_empty_features=True
        )
        self.scaler = StandardScaler()
        base = training[self.features].to_numpy(float)
        if self.mode == "history_logistic":
            base = np.column_stack([base, lags])
        x = (
            base
            if self.mode in {"noise_control", "history_logistic"}
            else np.column_stack([base, means])
        )
        real = self.scaler.fit_transform(self.imputer.fit_transform(x))
        self.training_n = len(training)
        self.synthetic = None
        if self.mode == "wm_augmented":
            states = posterior_draws(
                means, covariances, training.meeting_id, self.train_draws, self.seed
            )
            expanded = np.repeat(x[:, None, :], self.train_draws, axis=1)
            expanded[:, :, len(self.features) : len(self.features) + means.shape[1]] = states
            inputs = self.scaler.transform(self.imputer.transform(expanded.reshape(-1, x.shape[1])))
            labels = np.repeat(training.target_class.to_numpy(), self.train_draws)
            weights = np.full(len(inputs), 1 / self.train_draws)
            self.synthetic = pd.DataFrame(
                states.reshape(-1, means.shape[1]),
                columns=[f"latent_{i}" for i in range(means.shape[1])],
            )
            self.synthetic["parent_meeting_id"] = np.repeat(
                training.meeting_id.to_numpy(), self.train_draws
            )
            self.synthetic["observed_parent_class"] = labels
            self.synthetic["training_weight"] = weights
            self.synthetic["data_kind"] = "synthetic_latent_draw"
        elif self.mode == "noise_control":
            # Generic augmentation control; zero noise on missingness indicator columns.
            rng = np.random.default_rng(self.seed)
            noise = rng.normal(size=(len(real), self.train_draws // 2, real.shape[1]))
            noise = np.concatenate([noise, -noise], axis=1) * self.noise_scale
            noise[:, :, len(self.features) :] = 0
            inputs = (real[:, None, :] + noise).reshape(-1, real.shape[1])
            labels = np.repeat(training.target_class.to_numpy(), self.train_draws)
            weights = np.full(len(inputs), 1 / self.train_draws)
        else:
            inputs, labels, weights = real, training.target_class, np.ones(len(training))
        self.total_training_weight = float(weights.sum())
        self.classifier = LogisticRegression(C=self.C, solver="lbfgs", max_iter=2000)
        self.classifier.fit(inputs, labels, sample_weight=weights)
        return self

    def predict_proba(self, frame, means, covariances, lags=None):
        base = frame[self.features].to_numpy(float)
        if self.mode == "history_logistic":
            base = np.column_stack([base, lags])
        if self.mode in {"wm_integrated", "wm_augmented"}:
            states = posterior_draws(
                means, covariances, frame.meeting_id, self.prediction_draws, self.seed + 1
            )
            inputs = np.concatenate(
                [np.repeat(base[:, None, :], self.prediction_draws, axis=1), states], axis=2
            )
            inputs = inputs.reshape(-1, inputs.shape[2])
            raw = self.classifier.predict_proba(
                self.scaler.transform(self.imputer.transform(inputs))
            )
            raw = raw.reshape(len(frame), self.prediction_draws, -1).mean(axis=1)
        else:
            inputs = (
                base
                if self.mode in {"noise_control", "history_logistic"}
                else np.column_stack([base, means])
            )
            raw = self.classifier.predict_proba(
                self.scaler.transform(self.imputer.transform(inputs))
            )
        aligned = np.zeros((len(frame), 3))
        for i, label in enumerate(self.classifier.classes_):
            aligned[:, CLASSES.index(label)] = raw[:, i]
        return validate_probabilities(aligned)
