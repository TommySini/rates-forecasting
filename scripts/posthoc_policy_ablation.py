"""Post-hoc ablation, written after the structured-policy test scores were seen.

Not a registered comparison and not used for any selection. It locates which part
of the ordered model carries the test improvement, with no tuning on test.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import minimize

from rates_forecasting.evaluation.metrics import score_rows, summary
from rates_forecasting.evaluation.run import training_rows
from rates_forecasting.evaluation.tuning import resolve_split
from rates_forecasting.models.policy import (
    OrderedFree,
    TaylorOrdered,
    at_lower_bound,
    class_codes,
    ordered_loss,
    ordered_probabilities,
)


class MomentumOrdered:
    """Three parameters: two thresholds and the previous scheduled move."""

    def objective(self, theta, m, y, bound):
        loss, d_tau, d_gap, d_z = ordered_loss(theta[0], theta[1], theta[2] * m, y, bound)
        weak = (theta - [0.0, np.log(2.0), 0.0]) / [10.0, 2.0, 2.0]
        grad = np.array([d_tau, d_gap, d_z @ m]) + weak / [10.0, 2.0, 2.0]
        return loss + 0.5 * weak @ weak, grad

    def fit(self, d):
        m = d.previous_scheduled_bps.to_numpy() / 25
        args = (m, class_codes(d), at_lower_bound(d))
        start = np.array([0.0, np.log(2.0), 0.0])
        self.theta = minimize(self.objective, start, args=args, jac=True, method="L-BFGS-B").x
        return self

    def predict_proba(self, d):
        z = self.theta[2] * d.previous_scheduled_bps.to_numpy() / 25
        return ordered_probabilities(self.theta[0], self.theta[1], z, at_lower_bound(d))


config = yaml.safe_load(Path("configs/extended_2000.yaml").read_text())
panel = pd.read_parquet("data/processed/extended_2000/panel.parquet")
config, _, _ = resolve_split(panel, config)
ev = config["evaluation"]
test = panel[panel.decision_date >= config["sample"]["holdout_start"]].sort_values(
    "forecast_timestamp"
)
variants = {
    "momentum_only_ordered": MomentumOrdered,
    "ordered_free_weak_ridge_C10": lambda: OrderedFree(10.0),
    "taylor_ordered_lambda0": lambda: TaylorOrdered(0.0),
}
rows = []
for name, make in variants.items():
    for _, row in test.iterrows():
        forecast = pd.DataFrame([row])
        p = make().fit(training_rows(panel, row.forecast_timestamp)).predict_proba(forecast)[0]
        rows.append(
            {
                "meeting_id": row.meeting_id,
                "forecast_timestamp": row.forecast_timestamp,
                "decision_date": row.decision_date,
                "previous_scheduled_bps": row.previous_scheduled_bps,
                "model_name": name,
                "actual_class": row.target_class,
                "p_cut": p[0],
                "p_hold": p[1],
                "p_hike": p[2],
            }
        )
scored = score_rows(
    pd.DataFrame(rows), ev["probability_clip"], ev["cut_component_weight"], ev["missed_cut_cost"]
)
scored.to_csv("reports/policy_posthoc_ablation_predictions.csv", index=False)
table = summary(scored)
table.to_csv("reports/policy_posthoc_ablation.csv", index=False)
print(table.to_string(index=False))
