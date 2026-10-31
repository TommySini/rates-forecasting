"""Synthetic regression fixtures for early history and isolated datasets."""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from rates_forecasting.evaluation.tuning import resolve_split
from rates_forecasting.features.panel import build_panel
from rates_forecasting.paths import dataset_path


def test_unknown_early_publication_stays_missing_and_utc(config):
    config["sample"]["start"] = "2000-01-01"
    events = pd.DataFrame(
        {
            "meeting_id": ["SYNTHETIC-2001"],
            "scheduled_status": ["scheduled"],
            "scheduled_decision_date": ["2001-01-31"],
            "decision_date": ["2001-01-31"],
            "decision_class": ["cut"],
            "decision_published_at": [pd.NaT],
            "label_available_at": pd.to_datetime(["2001-02-01T23:00Z"]),
            "policy_rate_after": [5.5],
            "rate_change_bps": [-50.0],
            "verification_status": ["announcement_parsed"],
        }
    )
    observations = pd.DataFrame(
        columns=["series_id", "observation_period", "vintage_start", "value"]
    )
    observations["available_at"] = pd.Series([], dtype="datetime64[ns, UTC]")
    panel, lineage = build_panel(events, observations, config)
    assert panel.target_decision_timestamp.isna().all()
    assert str(panel.target_decision_timestamp.dtype) == "datetime64[ns, UTC]"
    assert panel.target_label_available_at.iloc[0] == pd.Timestamp("2001-02-01T23:00Z")
    assert panel.policy_midpoint.isna().all()  # No future target used as a policy feature.
    assert len(lineage) == 19


def test_expanded_fraction_split_keeps_early_cycle_in_training(config):
    rows = []
    for year in range(2000, 2026):
        for month in range(1, 8 if year == 2020 else 9):
            date = datetime(year=year, month=month, day=15, tzinfo=UTC)
            rows.append(
                {
                    "meeting_id": f"SYNTHETIC-{year}-{month}",
                    "decision_date": date.date().isoformat(),
                    "forecast_timestamp": date - timedelta(days=7),
                    "target_class": "cut" if year == 2001 else "hold",
                }
            )
    config["sample"]["fractions"] = {"training": 0.75, "development": 0.125, "test": 0.125}
    _, ledger, summary = resolve_split(pd.DataFrame(rows), config)
    assert summary.n.tolist() == [155, 26, 26]
    assert ledger.loc[ledger.decision_date.str.startswith("2001"), "split"].eq("training").all()
    assert ledger.loc[ledger.split == "development", "decision_date"].min().startswith("2019")


def test_expanded_artifacts_cannot_overwrite_original():
    original = dataset_path({}, "processed", "panel.parquet")
    expanded = dataset_path({"dataset": "extended_2000"}, "processed", "panel.parquet")
    assert str(original) == "data/processed/panel.parquet"
    assert str(expanded) == "data/processed/extended_2000/panel.parquet"
    assert original != expanded
    with pytest.raises(ValueError, match="Dataset name"):
        dataset_path({"dataset": "../"}, "processed", "panel.parquet")
