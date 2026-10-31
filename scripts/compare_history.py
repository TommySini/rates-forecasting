"""Prespecified early-history comparison; no downloads or post-test tuning."""

import copy
import json
from pathlib import Path

import pandas as pd
import yaml

from rates_forecasting.evaluation.metrics import paired_differences
from rates_forecasting.evaluation.run import evaluate
from rates_forecasting.evaluation.tuning import resolve_split
from rates_forecasting.paths import dataset_path


def main():
    config = yaml.safe_load(Path("configs/extended_2000.yaml").read_text())
    panel = pd.read_parquet(dataset_path(config, "processed", "panel.parquet"))
    resolved, _, _ = resolve_split(panel, config)
    fixed_dates = copy.deepcopy(resolved)
    fixed_dates["sample"].pop("fractions")
    primary = evaluate(panel, config)
    selected = json.loads((primary / "selected_models.json").read_text())
    control_panel = panel[panel.decision_date >= "2006-01-01"].reset_index(drop=True)
    control_config = copy.deepcopy(fixed_dates)
    control_config["sample"]["start"] = "2006-01-01"
    control = evaluate(control_panel, control_config, variant="extended_2000_control2006")
    # Remove the 2001 decisions from training examples; all real policy history
    # still enters eligible feature snapshots. Do not move development/test dates.
    no2001_panel = panel[~panel.decision_date.str.startswith("2001-")].reset_index(drop=True)
    no2001 = evaluate(no2001_panel, fixed_dates, variant="extended_2000_no2001", choices=selected)
    runs = {"expanded": primary, "control_2006": control, "omit_2001_fixed_settings": no2001}
    comparison, diagnostics, predictions = [], [], []
    reference_ids = None
    for label, root in runs.items():
        table = pd.read_csv(root / "model_comparison.csv")
        table["experiment"] = label
        comparison.append(table)
        cuts = pd.read_csv(root / "cut_diagnostics.csv")
        cuts["experiment"] = label
        diagnostics.append(cuts)
        pred = pd.read_parquet(root / "predictions.parquet")
        ids = set(pred.meeting_id)
        if reference_ids is not None and ids != reference_ids:
            raise ValueError("History comparisons must use exactly the same test meetings")
        reference_ids = ids
        pred["experiment"] = label
        predictions.append(pred)
    output = dataset_path(config, "reports", "history_comparison.csv").parent
    pd.concat(comparison, ignore_index=True).to_csv(output / "history_comparison.csv", index=False)
    pd.concat(diagnostics, ignore_index=True).to_csv(
        output / "history_cut_diagnostics.csv", index=False
    )
    contrasts = []
    combined = pd.concat(predictions, ignore_index=True)
    ev = config["evaluation"]
    for name, frame in combined.groupby("model_name"):
        frame = frame.copy()
        frame["model_name"] = frame.experiment
        differences = paired_differences(
            frame, ev["bootstrap_replicates"], ev["block_length_meetings"], ev["seed"]
        )
        differences["forecast_model"] = name
        contrasts.append(differences)
    pd.concat(contrasts).to_csv(output / "history_paired_differences.csv", index=False)
    (output / "history_runs.json").write_text(
        json.dumps({k: str(v) for k, v in runs.items()}, indent=2)
    )
    print(json.dumps({k: str(v) for k, v in runs.items()}, indent=2))


if __name__ == "__main__":
    main()
