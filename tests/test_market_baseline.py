"""Synthetic fixtures only: market mapping, chronology and probability accounting."""

import numpy as np
import pandas as pd
import pytest

from rates_forecasting.data.market_baseline import (
    _selected,
    compatible_direction,
    known_policy,
    partition_distribution,
    reviewed_poly_event,
    threshold_distribution,
)


def test_overlapping_thresholds_are_differenced_not_normalized():
    np.testing.assert_allclose(threshold_distribution(0.8, 0.1), [0.2, 0.7, 0.1])
    np.testing.assert_allclose(threshold_distribution(1, 1), [0, 0, 1])
    for a, b in [(0.1, 0.2), (np.nan, 0.1), (1.1, 0.1), (0.5, -0.1)]:
        with pytest.raises(ValueError):
            threshold_distribution(a, b)


@pytest.fixture
def partition():
    return pd.DataFrame(
        {
            "event_id": ["SYNTHETIC-EVENT"] * 4,
            "contract_id": ["A", "B", "C", "D"],
            "bucket": ["50+ bps decrease", "25 bps decrease", "no change", "25+ bps increase"],
            "target_definition": ["scheduled_upper_target_change"] * 4,
            "price": [0.1, 0.2, 0.68, 0.01],
        }
    )


def test_only_reviewed_related_complete_partition_can_be_reconciled(partition):
    p = partition_distribution(partition, reviewed=True, max_sum_error=0.05)
    np.testing.assert_allclose(p, np.array([0.3, 0.68, 0.01]) / 0.99)
    projected = partition_distribution(
        partition, reviewed=True, max_sum_error=0.05, method="simplex"
    )
    assert projected.sum() == pytest.approx(1) and (projected >= 0).all()
    for changed in [
        partition.assign(
            event_id=["OTHER", "SYNTHETIC-EVENT", "SYNTHETIC-EVENT", "SYNTHETIC-EVENT"]
        ),
        partition.iloc[:-1],
        partition.assign(contract_id=["A", "A", "C", "D"]),
        partition.assign(target_definition="year_end_rate"),
        partition.assign(price=[0.1, 0.2, np.nan, 0.01]),
        partition.assign(price=[0.1, 0.2, 0.4, 0.01]),
        partition.assign(bucket=["Other", "25 bps decrease", "no change", "25+ bps increase"]),
    ]:
        with pytest.raises(ValueError):
            partition_distribution(changed, reviewed=True, max_sum_error=0.05)
    with pytest.raises(ValueError):
        partition_distribution(partition, reviewed=False, max_sum_error=0.05)


def test_cutoff_selects_past_quote_and_never_fills_from_future():
    cutoff = pd.Timestamp("2025-09-10T22:00:00Z")
    data = [
        {"quote_timestamp": cutoff - pd.Timedelta(hours=1), "price": 0.2},
        {"quote_timestamp": cutoff + pd.Timedelta(seconds=1), "price": 0.99},
    ]
    config = {"maximum_sample_age_hours": 24}
    assert _selected(data, cutoff, config)["price"] == 0.2
    with pytest.raises(ValueError, match="missing"):
        _selected(data[1:], cutoff, config)
    with pytest.raises(ValueError, match="stale"):
        _selected(data[:1], cutoff + pd.Timedelta(days=2), config)


def test_forecast_target_is_known_policy_not_future_decision():
    cutoff = pd.Timestamp("2025-09-10T22:00Z")
    events = pd.DataFrame(
        {
            "label_available_at": [cutoff - pd.Timedelta(days=40), cutoff + pd.Timedelta(days=7)],
            "target_upper_after": [4.5, 4.25],
        }
    )
    assert known_policy(events, cutoff).target_upper_after == 4.5
    events.loc[1, "target_upper_after"] = 100
    assert known_policy(events, cutoff).target_upper_after == 4.5


def test_emergency_and_range_width_change_prevent_level_mapping():
    meeting = pd.Series(
        {
            "target_lower_before": 4.25,
            "target_upper_before": 4.5,
            "target_lower_after": 4,
            "target_upper_after": 4.25,
        }
    )
    policy = pd.Series({"target_upper_after": 4.5})
    compatible_direction(meeting, policy, False, level_target=True)
    with pytest.raises(ValueError, match="intervening"):
        compatible_direction(meeting, policy, True, level_target=True)
    # An immediately-before/after change contract can remain valid after an emergency move.
    compatible_direction(meeting, policy, True, level_target=False)
    meeting["target_lower_after"] = 3.75
    with pytest.raises(ValueError, match="width"):
        compatible_direction(meeting, policy, False, level_target=False)


def test_rule_changes_and_wrong_meeting_are_rejected(partition):
    rules = (
        "Upper bound versus prior to the meeting, rounded up to the nearest 25; "
        'otherwise the "No change" bracket.'
    )
    event = {
        "endDate": "2025-09-17T12:00Z",
        "markets": [
            {"groupItemTitle": bucket, "description": rules} for bucket in partition.bucket
        ],
    }
    reviewed_poly_event(event, "2025-09-17")
    with pytest.raises(ValueError, match="reviewed version"):
        reviewed_poly_event(event, "2025-09-17", expected_rule_hash="changed")
    with pytest.raises(ValueError, match="date"):
        reviewed_poly_event(event, "2025-09-18")
    event["markets"][0]["description"] = "A different binary event"
    with pytest.raises(ValueError, match="Different rules"):
        reviewed_poly_event(event, "2025-09-17")
