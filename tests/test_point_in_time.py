import numpy as np
import pandas as pd
import pytest

from rates_forecasting.features.panel import asof_observations, intervening_change, validate_panel


def test_future_revision_and_future_period_never_enter(synthetic_observations):
    frame = asof_observations(synthetic_observations, pd.Timestamp("2019-07-24T22:00Z"))
    assert frame.value.tolist() == [100]
    assert frame.observation_period.tolist() == ["2019-06-01"]


def test_observation_date_is_not_release_date(synthetic_observations):
    assert asof_observations(synthetic_observations, pd.Timestamp("2019-06-30T22:00Z")).empty
    assert asof_observations(synthetic_observations, pd.Timestamp("2019-07-08T21:59Z")).empty


def test_missing_revision_does_not_resurrect_old_value(synthetic_observations):
    synthetic_observations.loc[1, "value"] = np.nan
    result = asof_observations(synthetic_observations, pd.Timestamp("2019-08-06T22:00Z"))
    assert pd.isna(result.loc[result.observation_period == "2019-06-01", "value"]).all()


def test_cutoff_requires_timezone(synthetic_observations):
    with pytest.raises(ValueError, match="timezone"):
        asof_observations(synthetic_observations, pd.Timestamp("2019-07-24"))


def test_extra_lag_changes_eligibility(synthetic_observations):
    cutoff = pd.Timestamp("2019-07-08T22:00Z")
    assert len(asof_observations(synthetic_observations, cutoff)) == 1
    assert asof_observations(synthetic_observations, cutoff, lag=2).empty


def test_intervening_emergency_change():
    events = pd.DataFrame(
        {
            "scheduled_status": ["unscheduled"],
            "rate_change_bps": [-100.0],
            "decision_date": ["2020-03-15"],
            "decision_published_at": pd.to_datetime(["2020-03-15T21:00Z"]),
        }
    )
    assert intervening_change(events, pd.Timestamp("2020-03-11T22:00Z"), "2020-03-18") is True
    assert intervening_change(events, pd.Timestamp("2020-04-22T22:00Z"), "2020-04-29") is False


def test_unknown_intraday_emergency_is_ambiguous():
    events = pd.DataFrame(
        {
            "scheduled_status": ["unscheduled"],
            "rate_change_bps": [-50.0],
            "decision_date": ["2020-03-11"],
            "decision_published_at": [pd.NaT],
        }
    )
    assert intervening_change(events, pd.Timestamp("2020-03-11T22:00Z"), "2020-03-18") is None


def test_duplicate_meeting_rejected():
    panel = pd.DataFrame({"meeting_id": ["SYNTHETIC-A", "SYNTHETIC-A"]})
    with pytest.raises(ValueError, match="Duplicate"):
        validate_panel(panel, pd.DataFrame(), pd.DataFrame())
