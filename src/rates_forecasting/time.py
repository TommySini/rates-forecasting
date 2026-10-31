"""Calendar conventions: New York wall time, US federal business days, UTC storage."""

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from pandas.tseries.holiday import USFederalHolidayCalendar

NY = ZoneInfo("America/New_York")


@lru_cache(maxsize=128)
def holidays(year):
    return set(USFederalHolidayCalendar().holidays(f"{year}-01-01", f"{year}-12-31").date)


def business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays(d.year)


def shift_business(d: date, n: int) -> date:
    step = 1 if n > 0 else -1
    for _ in range(abs(n)):
        d += timedelta(days=step)
        while not business_day(d):
            d += timedelta(days=step)
    return d


def at_ny(d: date | str, hour=18, minute=0) -> datetime:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return datetime.combine(d, time(hour, minute), NY).astimezone(UTC)


def forecast_time(decision_date: date | str) -> datetime:
    if isinstance(decision_date, str):
        decision_date = date.fromisoformat(decision_date)
    d = decision_date - timedelta(days=7)
    while not business_day(d):
        d -= timedelta(days=1)
    return at_ny(d)


def vintage_availability(vintage_start: str, lag=1) -> datetime:
    if lag < 1:
        raise ValueError("Unknown intraday release requires at least one business day")
    return at_ny(shift_business(date.fromisoformat(vintage_start), lag))
