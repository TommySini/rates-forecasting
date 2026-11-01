"""Independent checks of a completed structured-policy run."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from rates_forecasting.evaluation.metrics import score_rows
from rates_forecasting.evaluation.policy import predict, references, select
from rates_forecasting.evaluation.run import training_rows
from rates_forecasting.evaluation.tuning import resolve_split
from rates_forecasting.models.baselines import validate_probabilities
from rates_forecasting.models.policy import LOWER_BOUND_MIDPOINT

out = Path(sys.argv[1])
complete = json.loads((out / "complete.json").read_text())
specification = json.loads((out / "specification.json").read_text())
config = specification["base"]
ev = config["evaluation"]
panel = pd.read_parquet(Path("data/processed") / config["dataset"] / "panel.parquet")
_, split, _ = resolve_split(panel, yaml.safe_load(Path(specification["base_config"]).read_text()))
test_ids = set(split.loc[split.split == "test", "meeting_id"])
dev_ids = set(split.loc[split.split == "development", "meeting_id"])
checks = []

predictions = pd.read_parquet(out / "predictions.parquet")
validate_probabilities(predictions[["p_cut", "p_hold", "p_hike"]].to_numpy())
rescored = score_rows(
    predictions.drop(columns=["brier", "cut_weighted_brier", "log_loss"]),
    ev["probability_clip"],
    ev["cut_component_weight"],
    ev["missed_cut_cost"],
)
for column in ["brier", "cut_weighted_brier", "log_loss"]:
    assert np.allclose(rescored[column], predictions[column]), column
for name, frame in predictions.groupby("model_name"):
    assert set(frame.meeting_id) == test_ids and len(frame) == len(test_ids), name
checks.append("valid probabilities, recomputed scores, identical real test meetings per model")

for run, file, names in references(specification):
    source = pd.read_parquet(Path(run) / file)
    for name, reported in names.items():
        copied = predictions[predictions.model_name == reported].set_index("meeting_id")
        frame = source[source.model_name == name].set_index("meeting_id").loc[copied.index]
        assert np.array_equal(
            frame[["p_cut", "p_hold", "p_hike"]].to_numpy(),
            copied[["p_cut", "p_hold", "p_hike"]].to_numpy(),
        ), name
checks.append("frozen reference predictions copied unchanged")

fresh = predictions[predictions.model_name.isin(specification["grids"])]
starts = specification.get("training_start", {})
for row in fresh.itertuples():
    eligible = training_rows(panel, row.forecast_timestamp)
    if row.model_name in starts:
        eligible = eligible[eligible.decision_date >= starts[row.model_name]]
    assert row.training_cutoff < row.forecast_timestamp
    assert row.training_n == len(eligible)
checks.append("every new forecast trains only on labels available before issuance")

table = pd.read_csv(out / "cv_candidates.csv")
selected = json.loads((out / "selected_models.json").read_text())
assert select(table) == selected == complete["selected"]
for name, value in selected.items():
    assert value in specification["grids"][name]
history = [
    json.loads(line)
    for line in Path("reports/policy_model_evaluation_history.jsonl").read_text().splitlines()
]
entry = next(h for h in history if h["fingerprint"] == complete["fingerprint"])
assert entry["selected"] == selected and entry["started_at"] < complete["completed_at"]
checks.append("selection recomputed from CV table and logged before test completion")

cv = pd.read_parquet(out / "cv_predictions.parquet")
assert set(cv.meeting_id) <= dev_ids and not set(cv.meeting_id) & test_ids
cv = cv.merge(panel[["meeting_id", "policy_midpoint"]], on="meeting_id")
ordered = cv[cv.model_name != "small_logistic"]
bound = ordered.policy_midpoint <= LOWER_BOUND_MIDPOINT + 1e-9
assert bound.any() and (ordered.loc[bound, "p_cut"] == 0).all()
checks.append("CV uses development meetings only; lower-bound meetings receive zero cut mass")

for meeting_id in sorted(test_ids)[::9]:
    row = panel[panel.meeting_id == meeting_id].iloc[0]
    train = training_rows(panel, row.forecast_timestamp)
    for name, value in selected.items():
        refit, _ = predict(train, pd.DataFrame([row]), name, value, config, specification)
        p = refit[["p_cut", "p_hold", "p_hike"]].to_numpy()
        stored = fresh[(fresh.model_name == name) & (fresh.meeting_id == meeting_id)]
        assert np.allclose(p, stored[["p_cut", "p_hold", "p_hike"]].to_numpy(), atol=1e-8), name
checks.append("independent refits reproduce sampled test forecasts")

result = {"status": "passed", "run": str(out), "checks": checks}
(out / "verification.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
