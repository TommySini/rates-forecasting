import pytest

from rates_forecasting.data.cache import Response
from rates_forecasting.data.fed import calendar_dates, decision_label, parse_statement, parse_target


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "The Committee raises its target for the federal funds rate to 5-3/4 percent.",
            (5.75, 5.75),
        ),
        ("Set the target range for the federal funds rate to 0 to 1/4 percent.", (0, 0.25)),
        (
            "Maintain the current 0 to 1/4 percent target range for the federal funds rate.",
            (0, 0.25),
        ),
        ("Maintain the federal funds rate in a target range of 0 to 1/4 percent.", (0, 0.25)),
        (
            "Lower the target range for the federal funds rate by 1/2 percentage point, to 1 to 1‑1/4 percent.",
            (1, 1.25),
        ),
    ],
)
def test_announced_targets_not_effective_or_upper_only(text, expected):
    assert parse_target(text)[:2] == expected


def test_range_transition_and_emergency_before_target():
    assert decision_label(1, 1, 0, 0.25) == (-87.5, "cut")
    assert decision_label(0, 0.25, 0, 0.25) == (0, "hold")
    # Emergency cut already lowered the target; subsequent scheduled hold is hold.
    assert decision_label(1, 1.25, 1, 1.25)[1] == "hold"
    assert decision_label(0.25, 0.5, 0.5, 0.75) == (25, "hike")


def test_last_update_is_not_release_time():
    response = Response(
        b"<p>For immediate release. Target for the federal funds rate to 5 percent.</p>"
        b"<p>Last update: 2:15 PM</p>",
        {
            "url": "https://www.federalreserve.gov/test/20000103.htm",
            "retrieved_at": "2026-10-30T22:00Z",
            "cache_id": "SYNTHETIC",
        },
    )
    result = parse_statement(response)
    assert result["decision_published_at"] is None
    assert result["label_available_at"].isoformat() == "2000-01-04T23:00:00+00:00"


def test_cross_month_meeting():
    start, end = calendar_dates("April/May 30-1 Meeting - 2019", 2019)
    assert start.isoformat() == "2019-04-30" and end.isoformat() == "2019-05-01"


def test_release_header_overrides_misdated_url():
    response = Response(
        b'<p class="article__time">June 28, 2007</p>'
        b"<p>Target for the federal funds rate at 5-1/4 percent.</p>",
        {
            "url": "https://www.federalreserve.gov/test/20070618a.htm",
            "retrieved_at": "2026-10-30T22:00Z",
            "cache_id": "SYNTHETIC",
        },
    )
    assert parse_statement(response)["decision_date"] == "2007-06-28"
