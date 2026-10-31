from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from rates_forecasting.features.panel import FEATURES

CLASSES = ["cut", "hold", "hike"]


def validate_probabilities(p):
    p = np.asarray(p, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all():
        raise ValueError("Probabilities must be finite n-by-3 arrays in cut/hold/hike order")
    if (p < 0).any() or (p > 1).any() or not np.allclose(p.sum(axis=1), 1, atol=1e-10):
        raise ValueError("Probabilities must be nonnegative and sum to one")
    return p


class Frequency:
    def __init__(self, alpha=1.0):
        if alpha <= 0:
            raise ValueError("Positive smoothing required")
        self.alpha = alpha

    def fit(self, training_data):
        counts = training_data.target_class.value_counts().reindex(CLASSES, fill_value=0)
        self.p = (counts.to_numpy() + self.alpha) / (len(training_data) + 3 * self.alpha)
        return self

    def predict_proba(self, forecast_data):
        return validate_probabilities(np.tile(self.p, (len(forecast_data), 1)))


class Supervised:
    def __init__(self, name, parameter, config, features=None):
        self.features = features or FEATURES
        self.fallback = None
        parameters = parameter if isinstance(parameter, dict) else {}
        steps = [
            (
                "imputer",
                SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
            )
        ]
        if name == "logistic":
            steps += [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=parameters.get("C", parameter), solver="lbfgs", max_iter=2000
                    ),
                ),
            ]
        elif name == "trees":
            m = config["models"]
            steps.append(
                (
                    "model",
                    HistGradientBoostingClassifier(
                        max_depth=parameters.get("max_depth", m["tree_max_depth"]),
                        max_iter=parameters.get("max_iter", m["tree_max_iter"]),
                        min_samples_leaf=parameters.get(
                            "min_samples_leaf", m["tree_min_samples_leaf"]
                        ),
                        learning_rate=parameters.get("learning_rate", m["tree_learning_rate"]),
                        l2_regularization=parameters.get("l2_regularization", parameter),
                        early_stopping=False,
                        random_state=config["evaluation"]["seed"],
                    ),
                )
            )
        else:
            raise ValueError(name)
        self.pipeline = Pipeline(steps)

    def fit(self, training_data):
        self.fallback = None
        if training_data.target_class.nunique() < 2:
            self.fallback = Frequency().fit(training_data)
        else:
            self.pipeline.fit(training_data[self.features], training_data.target_class)
        return self

    def predict_proba(self, forecast_data):
        if self.fallback:
            return self.fallback.predict_proba(forecast_data)
        raw = self.pipeline.predict_proba(forecast_data[self.features])
        aligned = np.zeros((len(forecast_data), 3))
        for idx, label in enumerate(self.pipeline.classes_):
            aligned[:, CLASSES.index(label)] = raw[:, idx]
        return validate_probabilities(aligned)


def model(name, parameter, config, features=None):
    if name == "frequency":
        alpha = (
            parameter.get("alpha", config["models"]["frequency_alpha"])
            if isinstance(parameter, dict)
            else config["models"]["frequency_alpha"]
        )
        return Frequency(alpha)
    return Supervised(name, parameter, config, features)
