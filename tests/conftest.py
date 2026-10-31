"""Synthetic fixtures only. Never imported by empirical ingestion or evaluation."""

from pathlib import Path

import pandas as pd
import pytest
import yaml


@pytest.fixture
def config():
    return yaml.safe_load(Path("configs/baseline.yaml").read_text())


@pytest.fixture
def synthetic_observations():
    return pd.DataFrame(
        {
            "series_id": ["TEST", "TEST", "TEST"],
            "observation_period": ["2019-06-01", "2019-06-01", "2019-07-01"],
            "value": [100.0, 999.0, 110.0],
            "vintage_start": ["2019-07-05", "2019-08-02", "2019-08-02"],
            "available_at": pd.to_datetime(
                ["2019-07-08T22:00Z", "2019-08-05T22:00Z", "2019-08-05T22:00Z"]
            ),
        }
    )
