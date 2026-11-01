"""Synthetic fixtures for dating pre-archive daily yields by observation date."""

import pandas as pd
import pytest

from rates_forecasting.data.fred import Fred, assume_unrevised_before
from rates_forecasting.features.panel import asof_observations
from rates_forecasting.time import vintage_availability

FIRST = "2005-06-28"


def archive_rows():
    rows = []
    for period, vintage, value in [
        ("2003-03-05", FIRST, 1.50),  # pre-archive, first archived vintage
        ("2003-03-06", FIRST, 1.52),
        ("2003-03-06", "2012-01-03", 1.53),  # later genuine revision
        ("2005-07-01", "2005-07-05", 3.70),  # archived normally
    ]:
        rows.append(
            {
                "series_id": "DGS2",
                "observation_period": period,
                "value": value,
                "vintage_start": vintage,
                "vintage_start_is_interval_bound": vintage == FIRST,
                "available_at": vintage_availability(vintage, 1),
                "availability_method": "alfred_vintage_plus_1_business_day_18ET",
            }
        )
    return pd.DataFrame(rows)


def test_pre_archive_values_use_observation_date_plus_lag():
    frame = assume_unrevised_before(archive_rows(), FIRST)
    first = frame.iloc[0]
    assert first.vintage_start == "2003-03-05" and first.alfred_vintage_start == FIRST
    assert first.available_at == vintage_availability("2003-03-05", 1)
    assert first.availability_method.startswith("assumed_unrevised")
    assert not first.vintage_start_is_interval_bound
    # Later revisions and normally archived observations keep their ALFRED dating.
    assert frame.iloc[2].vintage_start == "2012-01-03"
    assert frame.iloc[3].vintage_start == "2005-07-05"
    assert frame.iloc[3].availability_method.startswith("alfred")


def test_assumed_values_respect_cutoff_and_later_revisions():
    frame = assume_unrevised_before(archive_rows(), FIRST)
    frame["available_at"] = pd.to_datetime(frame.available_at, utc=True)
    # 2003-03-05 becomes available 2003-03-06 18:00 New York (23:00 UTC).
    assert asof_observations(frame, pd.Timestamp("2003-03-06T22:59Z")).empty
    before = asof_observations(frame, pd.Timestamp("2003-03-06T23:00Z"))
    assert list(before.observation_period) == ["2003-03-05"]
    after = asof_observations(frame, pd.Timestamp("2003-03-07T23:30Z"))
    assert after.set_index("observation_period").value.to_dict() == {
        "2003-03-05": 1.50,
        "2003-03-06": 1.52,
    }
    revised = asof_observations(frame, pd.Timestamp("2012-01-05T00:00Z"))
    assert revised.set_index("observation_period").loc["2003-03-06", "value"] == 1.53


def test_lag_sensitivity_shifts_assumed_values_and_keeps_label():
    frame = assume_unrevised_before(archive_rows(), FIRST)
    frame["available_at"] = pd.to_datetime(frame.available_at, utc=True)
    lagged = asof_observations(frame, pd.Timestamp("2003-03-07T23:30Z"), lag=2)
    assert list(lagged.observation_period) == ["2003-03-05"]
    assert lagged.availability_method.iloc[0] == (
        "assumed_unrevised_daily_obs_plus_2_business_day_18ET"
    )


def test_assumption_is_refused_for_revised_monthly_series():
    class OfflineCache:
        offline = True

    with pytest.raises(ValueError, match="daily yields"):
        Fred(OfflineCache()).observations(
            "PAYEMS", "thousands", "2000-01-01", "2001-01-01", "2001-01-01", unrevised=True
        )


def test_optional_one_month_yield_only_with_its_series():
    from rates_forecasting.features.panel import FEATURES, feature_names, panel_features

    assert feature_names({"DGS3MO": {}}) == FEATURES
    assert feature_names({"DGS1MO": {}, "DGS3MO": {}}) == [*FEATURES, "yield_1m"]
    assert panel_features(pd.DataFrame(columns=FEATURES)) == FEATURES
    assert panel_features(pd.DataFrame(columns=[*FEATURES, "yield_1m"]))[-1] == "yield_1m"
