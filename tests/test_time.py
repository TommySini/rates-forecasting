import pytest

from rates_forecasting.time import forecast_time, vintage_availability


@pytest.mark.parametrize(
    "meeting,expected",
    [
        ("2019-07-31", "2019-07-24T22:00:00+00:00"),
        ("2019-01-30", "2019-01-23T23:00:00+00:00"),
        ("2024-03-20", "2024-03-13T22:00:00+00:00"),
        ("2024-11-07", "2024-10-31T22:00:00+00:00"),
        ("2020-03-15", "2020-03-06T23:00:00+00:00"),  # weekend rolls before DST
        ("2024-07-11", "2024-07-03T22:00:00+00:00"),  # Independence Day
    ],
)
def test_forecast_calendar(meeting, expected):
    assert forecast_time(meeting).isoformat() == expected


def test_unknown_release_lag_holiday_weekend():
    assert vintage_availability("2024-05-24").isoformat() == "2024-05-28T22:00:00+00:00"
    assert vintage_availability("2019-07-05").isoformat() == "2019-07-08T22:00:00+00:00"
    with pytest.raises(ValueError):
        vintage_availability("2019-07-05", 0)
