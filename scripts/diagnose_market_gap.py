"""Post-hoc audit of frozen market/tree forecasts; no new test-set model selection.

Refits the recorded trees exactly, reconstructs their logits from saved-in-memory
tree nodes, inspects dated feature lineage, bounds Kalshi scores within recorded
bid/ask spreads, and checks the existing search with per-meeting development refits.
The latter uses development labels only and never scores its winner on test data.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import softmax
from threadpoolctl import threadpool_limits

from rates_forecasting.evaluation.metrics import score_rows, summary
from rates_forecasting.evaluation.run import training_rows
from rates_forecasting.evaluation.tuning import candidates
from rates_forecasting.models.baselines import CLASSES, model

BASELINE = Path("reports/runs/extended_2000-b4a00efeac35")
MARKETS = Path("reports/market_baseline_runs/176b1d70bbfe")
YIELDS = Path("reports/policy_model_runs/24f35e51a919")
EXAMPLE = "FOMC-2025-09-17"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_decomposition(fitted, row):
    """Exact contributions for the frozen depth-one, numeric sklearn trees.

    Uses the pinned sklearn representation; assertions below independently match
    sklearn probabilities. Contributions are logits, not causal economic effects.
    """
    estimator = fitted.pipeline["model"]
    names = fitted.pipeline["imputer"].get_feature_names_out()
    values = fitted.pipeline["imputer"].transform(row[fitted.features])[0]
    contributions = defaultdict(lambda: np.zeros(3))
    splits = Counter()
    for stage in estimator._predictors:
        for k, tree in enumerate(stage):
            root = tree.nodes[0]
            assert not root["is_categorical"]
            assert tree.nodes["depth"].max() <= 1
            name = "intercept" if root["is_leaf"] else names[root["feature_idx"]]
            if not root["is_leaf"]:
                splits[name, str(estimator.classes_[k])] += 1
            index = 0
            while not tree.nodes[index]["is_leaf"]:
                node = tree.nodes[index]
                value = values[node["feature_idx"]]
                left = (
                    bool(node["missing_go_to_left"])
                    if np.isnan(value)
                    else value <= node["num_threshold"]
                )
                index = node["left"] if left else node["right"]
            contributions[name][k] += tree.nodes[index]["value"]
    baseline = estimator._baseline_prediction[0]
    probability = softmax(baseline + sum(contributions.values()))
    np.testing.assert_allclose(
        probability, fitted.pipeline.predict_proba(row[fitted.features])[0], atol=1e-12
    )
    class_indices = [list(estimator.classes_).index(c) for c in CLASSES]
    records = [{"feature": "initial_intercept", **dict(zip(CLASSES, baseline[class_indices]))}] + [
        {"feature": name, **dict(zip(CLASSES, value[class_indices]))}
        for name, value in contributions.items()
    ]
    counts = [
        {"feature": name, "class": label, "split_count": count}
        for (name, label), count in splits.items()
    ]
    return records, counts, softmax(baseline)[class_indices]


def quote_bounds(quotes, market):
    """Outcome-dependent score bounds, not forecasts or confidence intervals."""
    rows = []
    for prediction in market[market.model_name.eq("kalshi")].itertuples():
        q = quotes[
            quotes.provider.eq("kalshi") & quotes.meeting_id.eq(prediction.meeting_id)
        ].set_index("role")
        a, b = q.loc["lower"], q.loc["current"]
        vertices = [(x, y) for x, y in product([a.bid, a.ask], [b.bid, b.ask]) if x >= y]
        # Include intersections with the monotonicity boundary a=b.
        vertices += [
            (v, v)
            for v in [a.bid, a.ask, b.bid, b.ask]
            if a.bid <= v <= a.ask and b.bid <= v <= b.ask
        ]
        assert vertices
        p = np.array([[1 - x, x - y, y] for x, y in vertices])
        actual = np.eye(3)[CLASSES.index(prediction.actual_class)]
        # Convex squared error attains a maximum at a feasible polygon vertex.
        worst = np.square(p - actual).sum(axis=1).max()
        rows.append(
            {
                "meeting_id": prediction.meeting_id,
                "cut_lower": 1 - a.ask,
                "cut_upper": 1 - a.bid,
                "midpoint_brier": prediction.brier,
                "worst_brier_inside_recorded_spreads": worst,
                "all_vertices_correct": bool((p.argmax(axis=1) == actual.argmax()).all()),
            }
        )
    return pd.DataFrame(rows)


def development_protocol_check(panel, config, features, out):
    # Freeze the pre-test subset before building any training/validation frames.
    pretest = panel[panel.decision_date < config["sample"]["holdout_start"]].copy()
    dev = pretest[pretest.decision_date >= config["sample"]["development_start"]]
    predictions = []
    grid = [(i, p) for i, (name, p) in enumerate(candidates(config)) if name == "trees"]
    for number, (index, parameters) in enumerate(grid, start=1):
        rows = []
        for _, point in dev.iterrows():
            training = training_rows(pretest, point.forecast_timestamp)
            assert training.target_label_available_at.max() < point.forecast_timestamp
            fitted = model("trees", parameters, config, features).fit(training)
            probability = fitted.predict_proba(pd.DataFrame([point]))[0]
            rows.append(
                {
                    "meeting_id": point.meeting_id,
                    "forecast_timestamp": point.forecast_timestamp,
                    "actual_class": point.target_class,
                    "model_name": "trees",
                    "candidate_id": f"trees-{index:03d}",
                    "candidate_parameters": json.dumps(parameters, sort_keys=True),
                    "training_n": len(training),
                    "training_cutoff": training.target_label_available_at.max(),
                    **dict(zip(["p_cut", "p_hold", "p_hike"], probability)),
                }
            )
        ev = config["evaluation"]
        predictions.append(
            score_rows(
                pd.DataFrame(rows),
                ev["probability_clip"],
                ev["cut_component_weight"],
                ev["missed_cut_cost"],
            )
        )
        if number % 12 == 0:
            print(f"Development-only protocol check: {number}/{len(grid)} candidates", flush=True)
    predictions = pd.concat(predictions, ignore_index=True)
    assert set(predictions.meeting_id) == set(dev.meeting_id)
    predictions.to_parquet(out / "development_refit_predictions.parquet", index=False)
    scores = summary(predictions, ("candidate_id", "candidate_parameters"))
    scores = scores.sort_values(["cut_weighted_brier", "brier", "candidate_id"])
    scores.to_csv(out / "development_refit_candidates.csv", index=False)
    original = pd.read_csv(BASELINE / "cv_candidates.csv")
    original = original[original.model_name.eq("trees")].sort_values(
        ["cut_weighted_brier", "brier", "candidate_id"]
    )
    selected = original.iloc[0].candidate_id
    corresponding = scores[scores.candidate_id.eq(selected)].iloc[0]
    return {
        "candidates": len(grid),
        "development_meetings": len(dev),
        "original_block_fit_winner": original.iloc[0].to_dict(),
        "per_meeting_fit_winner": scores.iloc[0].to_dict(),
        "original_winner_under_per_meeting_refits": corresponding.to_dict(),
        "test_predictions_for_new_selection": "not computed",
        "interpretation": "post-hoc diagnostic, not a replacement selected model",
    }


def run():
    inputs = [
        BASELINE / name
        for name in [
            "input_panel.parquet",
            "predictions.parquet",
            "selected_models.json",
            "resolved_config.json",
            "feature_set.csv",
            "cv_candidates.csv",
        ]
    ] + [
        MARKETS / "market_predictions.parquet",
        MARKETS / "quote_lineage.parquet",
        MARKETS / "matched_predictions.parquet",
        YIELDS / "predictions.parquet",
        Path("data/processed/extended_2000/lineage.parquet"),
        Path("data/interim/meeting_inventory.parquet"),
        Path("uv.lock"),
    ]
    source_paths = [
        Path(__file__),
        *[
            Path("src/rates_forecasting") / name
            for name in [
                "models/baselines.py",
                "evaluation/metrics.py",
                "evaluation/run.py",
                "evaluation/tuning.py",
                "features/panel.py",
            ]
        ],
    ]
    fingerprint = {str(p): sha(p) for p in inputs + source_paths}
    identifier = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:12]
    out = Path("reports/diagnostic_runs") / ("market_gap-" + identifier)
    if (out / "complete.json").exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    (out / "inputs.json").write_text(json.dumps(fingerprint, indent=2))
    panel = pd.read_parquet(BASELINE / "input_panel.parquet")
    config = json.loads((BASELINE / "resolved_config.json").read_text())
    features = pd.read_csv(BASELINE / "feature_set.csv").feature.tolist()
    parameters = json.loads((BASELINE / "selected_models.json").read_text())["trees"]
    saved = pd.read_parquet(BASELINE / "predictions.parquet")
    saved = saved[saved.model_name.eq("trees")]
    checks, contributions, splits = [], [], []
    example_training = None
    for recorded in saved.itertuples():
        row = panel[panel.meeting_id.eq(recorded.meeting_id)]
        training = training_rows(panel, row.forecast_timestamp.iloc[0])
        fitted = model("trees", parameters, config, features).fit(training)
        probability = fitted.predict_proba(row)[0]
        expected = np.array([recorded.p_cut, recorded.p_hold, recorded.p_hike])
        np.testing.assert_allclose(probability, expected, rtol=0, atol=1e-12)
        assert len(training) == recorded.training_n
        assert training.target_label_available_at.max() == recorded.training_cutoff
        terms, counts, prior = tree_decomposition(fitted, row)
        contributions += [{"meeting_id": recorded.meeting_id, **r} for r in terms]
        splits += [{"meeting_id": recorded.meeting_id, **r} for r in counts]
        checks.append(
            {
                "meeting_id": recorded.meeting_id,
                "training_n": len(training),
                "training_cutoff": recorded.training_cutoff,
                "maximum_probability_difference": float(np.abs(probability - expected).max()),
                **dict(zip(["prior_cut", "prior_hold", "prior_hike"], prior)),
                **dict(zip(["p_cut", "p_hold", "p_hike"], probability)),
            }
        )
        if recorded.meeting_id == EXAMPLE:
            example_training = training
    assert example_training is not None
    pd.DataFrame(checks).to_csv(out / "frozen_refit_checks.csv", index=False)
    pd.DataFrame(contributions).to_parquet(out / "exact_logit_contributions.parquet", index=False)
    pd.DataFrame(splits).to_csv(out / "tree_split_counts.csv", index=False)
    context = pd.crosstab(
        np.sign(example_training.previous_scheduled_bps), example_training.target_class
    )
    context.to_csv(out / "september_training_transitions.csv")
    lineage = pd.read_parquet("data/processed/extended_2000/lineage.parquet")
    for point in saved.itertuples():
        relevant = lineage[lineage.meeting_id.eq(point.meeting_id) & lineage.feature.isin(features)]
        assert relevant.feature.nunique() == len(features)
        for item in relevant.itertuples():
            for source in json.loads(item.inputs_json):
                assert pd.Timestamp(source["available_at"]) <= point.forecast_timestamp
    example = lineage[lineage.meeting_id.eq(EXAMPLE) & lineage.feature.isin(features)]
    example.to_parquet(out / "september_feature_lineage.parquet", index=False)
    # Independently verify the decisive labor features against the dated BLS release.
    values = example.set_index("feature").value
    assert np.isclose(values.payroll_1m, 22) and np.isclose(values.unemployment, 4.3)
    market = pd.read_parquet(MARKETS / "market_predictions.parquet")
    quotes = pd.read_parquet(MARKETS / "quote_lineage.parquet")
    bounds = quote_bounds(quotes, market)
    bounds.to_csv(out / "kalshi_spread_score_bounds.csv", index=False)
    paired = pd.read_parquet(MARKETS / "matched_predictions.parquet")
    differences = []
    for name, frame in paired.groupby("comparison"):
        trees = frame[frame.model_name.eq("trees")].set_index("meeting_id")
        for provider, other in frame[~frame.model_name.eq("trees")].groupby("model_name"):
            other = other.set_index("meeting_id").loc[trees.index]
            for meeting in trees.index:
                differences.append(
                    {
                        "comparison": name,
                        "provider": provider,
                        "meeting_id": meeting,
                        "tree_brier": trees.loc[meeting, "brier"],
                        "market_brier": other.loc[meeting, "brier"],
                        "tree_minus_market_brier": trees.loc[meeting, "brier"]
                        - other.loc[meeting, "brier"],
                    }
                )
    differences = pd.DataFrame(differences)
    differences.to_csv(out / "per_meeting_score_gaps.csv", index=False)
    # Include only previously computed controls, with no fitting or selection here.
    controls = pd.read_parquet(YIELDS / "predictions.parquet")
    controls = controls[
        controls.model_name.isin(["trees_17f", "market_ordered", "momentum_ordered"])
    ]
    matched = []
    for name, frame in paired.groupby("comparison"):
        ids = set(frame.meeting_id)
        joined = pd.concat([frame, controls[controls.meeting_id.isin(ids)]], ignore_index=True)
        assert not joined.duplicated(["meeting_id", "model_name"]).any()
        assert joined.groupby("model_name").size().eq(len(ids)).all()
        matched.append(joined.assign(comparison=name))
    matched = pd.concat(matched, ignore_index=True)
    summary(matched, ("comparison", "model_name")).to_csv(
        out / "existing_controls_matched.csv", index=False
    )
    matched[matched.meeting_id.eq(EXAMPLE)].drop_duplicates("model_name").to_csv(
        out / "september_existing_forecasts.csv", index=False
    )
    cv = development_protocol_check(panel, config, features, out)
    (out / "development_protocol_check.json").write_text(json.dumps(cv, indent=2))
    assert {str(p): sha(p) for p in inputs} == {str(p): fingerprint[str(p)] for p in inputs}
    result = {
        "status": "post_hoc_diagnostic_complete",
        "frozen_test_refits_checked": len(checks),
        "maximum_frozen_probability_difference": max(
            x["maximum_probability_difference"] for x in checks
        ),
        "exact_class_aligned_logit_reconstructions": len(checks),
        "feature_availability_checks": "all inputs to 12 used features at 26 cutoffs passed",
        "september_training_n": len(example_training),
        "september_training_class_counts": example_training.target_class.value_counts().to_dict(),
        "kalshi_midpoint_brier": float(bounds.midpoint_brier.mean()),
        "kalshi_worst_brier_within_recorded_spreads": float(
            bounds.worst_brier_inside_recorded_spreads.mean()
        ),
        "all_kalshi_spread_vertices_correct": bool(bounds.all_vertices_correct.all()),
        "development_protocol_winner_unchanged": cv["original_block_fit_winner"]["candidate_id"]
        == cv["per_meeting_fit_winner"]["candidate_id"],
        "test_predictions_for_new_selection": "not computed",
        "original_artifact_hashes_unchanged": True,
    }
    (out / "complete.json").write_text(json.dumps(result, indent=2))
    return out


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        print(run())
