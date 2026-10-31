"""Chronological split allocation and bounded, fully enumerated development CV."""

from __future__ import annotations

import copy
import json
from itertools import product

import numpy as np
import pandas as pd

from rates_forecasting.evaluation.metrics import score_rows
from rates_forecasting.models.baselines import CLASSES, model


def resolve_split(panel, config):
    """Largest-remainder rounding retains every meeting in exactly one ordered split."""
    config = copy.deepcopy(config)
    sample = config["sample"]
    ordered = panel.sort_values("forecast_timestamp").reset_index(drop=True)
    if ordered.meeting_id.duplicated().any() or ordered.forecast_timestamp.duplicated().any():
        raise ValueError("Duplicate meetings or forecast timestamps")
    if not ordered.decision_date.is_monotonic_increasing:
        raise ValueError("Decision and issuance order disagree")
    fractions = sample.get("fractions")
    if fractions:
        values = np.array([fractions.get(k, np.nan) for k in ("training", "development", "test")])
        if not np.isfinite(values).all() or (values <= 0).any() or not np.isclose(values.sum(), 1):
            raise ValueError("Training/development/test fractions must be positive and sum to one")
        exact = len(ordered) * values
        counts = np.floor(exact).astype(int)
        remainder = len(ordered) - counts.sum()
        for index in np.argsort(-(exact - counts), kind="stable")[:remainder]:
            counts[index] += 1
        if counts.min() < 1 or counts[0] < sample["minimum_train_meetings"]:
            raise ValueError("Insufficient meetings for requested split")
        a, b = counts[0], counts[0] + counts[1]
        sample["development_start"] = ordered.iloc[a].decision_date
        sample["holdout_start"] = ordered.iloc[b].decision_date
    elif not (
        sample["start"] < sample["development_start"] < sample["holdout_start"] <= sample["end"]
    ):
        raise ValueError("Invalid chronological split boundaries")
    ordered["split"] = np.select(
        [
            ordered.decision_date < sample["development_start"],
            ordered.decision_date < sample["holdout_start"],
        ],
        ["training", "development"],
        default="test",
    )
    ledger = ordered[["meeting_id", "decision_date", "forecast_timestamp", "target_class", "split"]]
    rows = []
    for name in ("training", "development", "test"):
        frame = ledger[ledger.split == name]
        if frame.empty:
            raise ValueError(f"Empty {name} split")
        counts = frame.target_class.value_counts()
        rows.append(
            {
                "split": name,
                "n": len(frame),
                "fraction": len(frame) / len(ordered),
                "first_decision": frame.decision_date.min(),
                "last_decision": frame.decision_date.max(),
                **{label: int(counts.get(label, 0)) for label in CLASSES},
            }
        )
    return config, ledger, pd.DataFrame(rows)


def development_folds(panel, config):
    sample = config["sample"]
    dev = panel[
        (panel.decision_date >= sample["development_start"])
        & (panel.decision_date < sample["holdout_start"])
    ].sort_values("forecast_timestamp")
    n_folds = config["evaluation"]["search"]["folds"]
    if not isinstance(n_folds, int) or not 2 <= n_folds <= len(dev):
        raise ValueError("CV requires at least two nonempty development folds")
    for fold, indices in enumerate(np.array_split(np.arange(len(dev)), n_folds), start=1):
        validation = dev.iloc[indices]
        cutoff = validation.forecast_timestamp.min()
        training = panel[
            (panel.forecast_timestamp < cutoff) & (panel.target_label_available_at < cutoff)
        ].sort_values("forecast_timestamp")
        if len(training) < sample["minimum_train_meetings"]:
            raise ValueError("Insufficient eligible training labels in CV fold")
        yield fold, training, validation


def candidates(config):
    search = config["evaluation"]["search"]
    grids = search["grids"]
    allowed = {
        "frequency": {"alpha"},
        "logistic": {"C"},
        "trees": {
            "max_depth",
            "max_iter",
            "learning_rate",
            "min_samples_leaf",
            "l2_regularization",
        },
    }
    if set(grids) != set(allowed):
        raise ValueError("Search must specify frequency, logistic and trees")
    result = []
    for name, grid in grids.items():
        if set(grid) != allowed[name] or any(not values for values in grid.values()):
            raise ValueError(f"Search must cover all supported statistical parameters for {name}")
        keys = sorted(grid)
        for values in product(*(grid[k] for k in keys)):
            result.append((name, dict(zip(keys, values))))
    if len(result) > search["max_candidates"]:
        raise ValueError("Declared full grid exceeds the tuning budget")
    return result


def cross_validate(panel, config, features):
    """No test rows, labels, or feature values enter fitting or candidate scoring."""
    ev = config["evaluation"]
    before_test = panel[panel.decision_date < config["sample"]["holdout_start"]].copy()
    folds = list(development_folds(before_test, config))
    manifests = []
    for fold, train, validation in folds:
        manifests.append(
            {
                "fold": fold,
                "training_n": len(train),
                "training_cutoff": train.target_label_available_at.max(),
                "validation_n": len(validation),
                "validation_first_forecast": validation.forecast_timestamp.min(),
                "validation_last_forecast": validation.forecast_timestamp.max(),
                **{
                    f"validation_{label}": int(validation.target_class.eq(label).sum())
                    for label in CLASSES
                },
                "fit_policy": "fit once before each validation block; expand between blocks",
            }
        )
    predictions, scores = [], []
    for index, (name, parameter) in enumerate(candidates(config)):
        candidate_id = f"{name}-{index:03d}"
        for fold, training, validation in folds:
            fitted = model(name, parameter, config, features).fit(training)
            p = fitted.predict_proba(validation)
            result = validation[["meeting_id", "forecast_timestamp", "decision_date"]].copy()
            result["actual_class"] = validation.target_class
            result["model_name"] = name
            result["candidate_id"] = candidate_id
            result["candidate_parameters"] = json.dumps(parameter, sort_keys=True)
            result["fold"] = fold
            result["training_n"] = len(training)
            result["training_cutoff"] = training.target_label_available_at.max()
            result[["p_cut", "p_hold", "p_hike"]] = p
            result = score_rows(
                result, ev["probability_clip"], ev["cut_component_weight"], ev["missed_cut_cost"]
            )
            predictions.append(result)
            scores.append(
                {
                    "model_name": name,
                    "candidate_id": candidate_id,
                    "candidate_parameters": json.dumps(parameter, sort_keys=True),
                    "fold": fold,
                    "n": len(result),
                    "brier": result.brier.mean(),
                    "cut_weighted_brier": result.cut_weighted_brier.mean(),
                    "log_loss": result.log_loss.mean(),
                }
            )
    predictions = pd.concat(predictions, ignore_index=True)
    table = predictions.groupby(
        ["model_name", "candidate_id", "candidate_parameters"], as_index=False
    ).agg(
        n=("brier", "size"),
        brier=("brier", "mean"),
        cut_weighted_brier=("cut_weighted_brier", "mean"),
        log_loss=("log_loss", "mean"),
    )
    # Weight meetings equally even if the last CV block is shorter. Stable tie break.
    selected = {}
    for name, frame in table.groupby("model_name", sort=False):
        best = frame.sort_values(["cut_weighted_brier", "brier", "candidate_id"]).iloc[0]
        selected[name] = json.loads(best.candidate_parameters)
    return selected, predictions, table, pd.DataFrame(scores), pd.DataFrame(manifests)
