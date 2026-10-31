from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from rates_forecasting.models.baselines import CLASSES


def plots(predictions, calibration, output):
    output = Path(output)
    names = list(predictions.model_name.unique())
    colors = {"cut": "#2563eb", "hold": "#626b73", "hike": "#dc6a23"}
    fig, axes = plt.subplots(
        len(names), 1, figsize=(12, 3 * len(names)), sharex=True, squeeze=False
    )
    for ax, name in zip(axes[:, 0], names):
        frame = predictions[predictions.model_name == name].sort_values("forecast_timestamp")
        dates = pd.to_datetime(frame.decision_date)
        for label in CLASSES:
            ax.plot(dates, frame["p_" + label], label=label, color=colors[label], linewidth=1.2)
            mask = frame.actual_class == label
            ax.scatter(dates[mask], [1.03] * mask.sum(), color=colors[label], s=14, marker="|")
        ax.set(ylim=(-0.03, 1.1), ylabel="Probability", title=name)
        ax.legend(ncol=3, loc="upper left")
    fig.suptitle("Seven-day forecasts • historical holdout\nTop ticks show realized decisions")
    fig.tight_layout()
    fig.savefig(output / "probabilities.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(len(names), 3, figsize=(12, 3.4 * len(names)), squeeze=False)
    for i, name in enumerate(names):
        for j, label in enumerate(CLASSES):
            ax = axes[i, j]
            frame = calibration[
                (calibration.model_name == name)
                & (calibration["class"] == label)
                & (calibration.n > 0)
            ]
            ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=0.8)
            ax.vlines(
                frame.mean_probability,
                frame.lower_95,
                frame.upper_95,
                color=colors[label],
                alpha=0.6,
            )
            ax.scatter(frame.mean_probability, frame.observed_frequency, color=colors[label])
            for r in frame.itertuples():
                ax.annotate(
                    f"n={r.n}",
                    (r.mean_probability, r.observed_frequency),
                    xytext=(3, 5),
                    textcoords="offset points",
                    fontsize=8,
                )
            ax.set(
                xlim=(-0.03, 1.03),
                ylim=(-0.05, 1.1),
                title=f"{name} / {label}",
                xlabel="Mean forecast",
                ylabel="Observed frequency",
            )
    fig.suptitle(
        "Calibration • 5 fixed bins\n95% circular block bootstrap intervals (8 meetings); sparse bins are uncertain"
    )
    fig.tight_layout()
    fig.savefig(output / "calibration.png", dpi=160)
    plt.close(fig)
