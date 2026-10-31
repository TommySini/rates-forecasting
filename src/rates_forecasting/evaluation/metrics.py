from __future__ import annotations

import numpy as np
import pandas as pd

from rates_forecasting.models.baselines import CLASSES, validate_probabilities


def score_rows(predictions, clip=1e-15, cut_weight=1.0, missed_cut_cost=2.0):
    if not np.isfinite(cut_weight) or cut_weight <= 0:
        raise ValueError("Cut component weight must be positive and finite")
    if not np.isfinite(missed_cut_cost) or missed_cut_cost < 1:
        raise ValueError("Missed-cut cost must be finite and at least one")
    result = predictions.copy()
    p = validate_probabilities(result[["p_cut", "p_hold", "p_hike"]].to_numpy())
    if not result.actual_class.isin(CLASSES).all():
        raise ValueError("Unknown actual class")
    y = np.array([CLASSES.index(x) for x in result.actual_class])
    onehot = np.eye(3)[y]
    errors = (p - onehot) ** 2
    result["brier"] = errors.sum(axis=1)
    result["cut_weighted_brier"] = errors @ np.array([cut_weight, 1.0, 1.0])
    result["log_loss"] = -np.log(np.clip(p[np.arange(len(p)), y], clip, 1))
    result["correct"] = p.argmax(axis=1) == y
    result["predicted_class"] = np.asarray(CLASSES)[p.argmax(axis=1)]
    # Minimize expected cost: a missed cut costs more; all other mistakes cost 1.
    # These are decision scores, never replacement probabilities.
    decision = (p * np.array([missed_cut_cost, 1.0, 1.0])).argmax(axis=1)
    result["cut_sensitive_class"] = np.asarray(CLASSES)[decision]
    result["cut_sensitive_cost"] = np.where(y == 0, missed_cut_cost, 1.0) * (decision != y)
    result["p_actual"] = p[np.arange(len(p)), y]
    return result


def summary(scored, group=("model_name",)):
    extra = (
        {"cut_weighted_brier": ("cut_weighted_brier", "mean")}
        if "cut_weighted_brier" in scored
        else {}
    )
    return (
        scored.groupby(list(group), dropna=False)
        .agg(
            n=("brier", "size"),
            brier=("brier", "mean"),
            log_loss=("log_loss", "mean"),
            accuracy=("correct", "mean"),
            **extra,
        )
        .reset_index()
    )


def cut_diagnostics(scored):
    """Keep argmax accuracy distinct from the user-requested cost-sensitive decision."""
    rows = []
    for name, frame in scored.groupby("model_name"):
        actual = frame.actual_class.eq("cut")
        for rule, column in [
            ("argmax", "predicted_class"),
            ("missed_cut_cost", "cut_sensitive_class"),
        ]:
            predicted = frame[column].eq("cut")
            tp = int((actual & predicted).sum())
            fp = int((~actual & predicted).sum())
            rows.append(
                {
                    "model_name": name,
                    "decision_rule": rule,
                    "n": len(frame),
                    "actual_cuts": int(actual.sum()),
                    "correct_cut_calls": tp,
                    "missed_cuts": int((actual & ~predicted).sum()),
                    "false_cut_calls": fp,
                    "cut_recall": tp / actual.sum() if actual.any() else np.nan,
                    "cut_precision": tp / (tp + fp) if tp + fp else np.nan,
                    "accuracy": frame[column].eq(frame.actual_class).mean(),
                }
            )
    return pd.DataFrame(rows)


def block_indices(n, block_length, rng):
    if n < 1:
        raise ValueError("No observations to bootstrap")
    length = min(n, block_length)
    starts = rng.integers(0, n, size=int(np.ceil(n / length)))
    return np.concatenate([(np.arange(length) + x) % n for x in starts])[:n]


def paired_differences(scored, replicates=1000, length=8, seed=0):
    wide = scored.pivot(
        index="forecast_timestamp", columns="model_name", values="brier"
    ).sort_index()
    rng = np.random.default_rng(seed)
    rows = []
    for reference in wide.columns:
        for name in wide.columns:
            if name <= reference:
                continue
            pair = wide[[name, reference]].dropna()
            d = (pair[name] - pair[reference]).to_numpy()
            draws = [d[block_indices(len(d), length, rng)].mean() for _ in range(replicates)]
            rows.append(
                {
                    "model": name,
                    "reference": reference,
                    "n": len(d),
                    "mean_brier_difference": d.mean(),
                    "lower_95": np.quantile(draws, 0.025),
                    "upper_95": np.quantile(draws, 0.975),
                    "block_length": length,
                    "method": "paired circular moving-block bootstrap; descriptive",
                }
            )
    return pd.DataFrame(rows)


def calibration(scored, bins=5, replicates=1000, length=8, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for name, frame in scored.groupby("model_name"):
        frame = frame.sort_values("forecast_timestamp")
        for label in CLASSES:
            p = frame["p_" + label].to_numpy()
            y = (frame.actual_class == label).to_numpy().astype(float)
            bucket = np.minimum((p * bins).astype(int), bins - 1)
            draws = {b: [] for b in range(bins)}
            for _ in range(replicates):
                ix = block_indices(len(frame), length, rng)
                for b in range(bins):
                    mask = bucket[ix] == b
                    if mask.any():
                        draws[b].append(y[ix][mask].mean())
            for b in range(bins):
                mask = bucket == b
                n = int(mask.sum())
                rows.append(
                    {
                        "model_name": name,
                        "class": label,
                        "bin": b,
                        "n": n,
                        "mean_probability": p[mask].mean() if n else np.nan,
                        "observed_frequency": y[mask].mean() if n else np.nan,
                        "lower_95": np.quantile(draws[b], 0.025) if draws[b] else np.nan,
                        "upper_95": np.quantile(draws[b], 0.975) if draws[b] else np.nan,
                        "bootstrap_nonempty": len(draws[b]),
                    }
                )
    return pd.DataFrame(rows)
