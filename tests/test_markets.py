import pandas as pd
import pytest

from rates_forecasting.data.markets import last_quote, map_distribution


def test_future_quote_excluded_and_age_recorded():
    q = pd.DataFrame(
        {
            "quote_timestamp": pd.to_datetime(["2024-09-10T20:00Z", "2024-09-12T20:00Z"]),
            "price": [0.2, 0.9],
        }
    )
    row, status = last_quote(q, pd.Timestamp("2024-09-11T22:00Z"))
    assert row["price"] == 0.2 and row["quote_age_hours"] == 26 and status == "stale"


def test_partition_and_target_required():
    c = pd.DataFrame(
        {
            "contract_id": ["SYN-C", "SYN-H", "SYN-U"],
            "outcome_class": ["cut", "hold", "hike"],
            "price": [0.2, 0.5, 0.3],
        }
    )
    for target, exclusive, exhaustive in [
        ("rate_level", True, True),
        ("scheduled_meeting_change", False, True),
        ("scheduled_meeting_change", True, False),
    ]:
        with pytest.raises(ValueError):
            map_distribution(
                c, target_definition=target, mutually_exclusive=exclusive, exhaustive=exhaustive
            )
    p = map_distribution(
        c, target_definition="scheduled_meeting_change", mutually_exclusive=True, exhaustive=True
    )
    assert p == {"cut": 0.2, "hold": 0.5, "hike": 0.3}
    c.price = [0.5, 0.5, 0.5]
    with pytest.raises(ValueError, match="normalize"):
        map_distribution(
            c,
            target_definition="scheduled_meeting_change",
            mutually_exclusive=True,
            exhaustive=True,
        )
