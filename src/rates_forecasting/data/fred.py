"""FRED v1/ALFRED real-time intervals, never a today's-history fallback."""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv

from rates_forecasting.data.cache import Cache, SourceUnavailable
from rates_forecasting.time import vintage_availability

API = "https://api.stlouisfed.org/fred/"


def assume_unrevised_before(frame, first_vintage, lag=1):
    """Date pre-archive daily values by observation, not by ALFRED's first vintage.

    Only for series configured as effectively unrevised (daily Treasury yields:
    at most 0.05% of archived observations ever change). Each value dated before
    the first archived vintage becomes available its observation date plus the
    usual unknown-time lag. The ALFRED vintage is kept and the method is labeled.
    """
    frame = frame.copy()
    frame["alfred_vintage_start"] = frame.vintage_start
    mask = (frame.vintage_start == first_vintage) & (frame.observation_period < first_vintage)
    periods = frame.loc[mask, "observation_period"]
    frame.loc[mask, "vintage_start"] = periods
    frame.loc[mask, "vintage_start_is_interval_bound"] = False
    frame.loc[mask, "available_at"] = pd.Series(
        [vintage_availability(p, lag) for p in periods], index=periods.index, dtype=object
    )
    frame.loc[mask, "availability_method"] = (
        f"assumed_unrevised_daily_obs_plus_{lag}_business_day_18ET"
    )
    return frame


class Fred:
    def __init__(self, cache: Cache):
        load_dotenv(".env", override=False)
        self.key = os.environ.get("FRED_API_KEY")
        self.cache = cache
        self.release_reviews = yaml.safe_load(
            Path("configs/release_timestamp_reviews.yaml").read_text()
        )

    def get(self, endpoint, **params):
        if not self.key and not self.cache.offline:
            raise SourceUnavailable(
                "FRED_API_KEY is required; configure local .env. No revised-history fallback."
            )
        return self.cache.get(
            API + endpoint, params | {"api_key": self.key or "", "file_type": "json"}
        )

    def audit_series(self, series_id):
        meta = self.get("series", series_id=series_id).json()["seriess"][0]
        dates = self.get(
            "series/vintagedates",
            series_id=series_id,
            limit=10000,
            realtime_start="1776-07-04",
            realtime_end="2025-12-31",
        ).json()
        vd = dates["vintage_dates"]
        return {
            "series_id": series_id,
            "title": meta["title"],
            "units": meta["units"],
            "frequency": meta["frequency"],
            "seasonal_adjustment": meta["seasonal_adjustment"],
            "observation_start": meta["observation_start"],
            "observation_end": meta["observation_end"],
            "earliest_vintage": min(vd) if vd else None,
            "latest_vintage_in_audit": max(vd) if vd else None,
            "vintage_count": dates["count"],
            "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
        }

    def observations(self, series_id, units, start, end, realtime_end, lag=1, unrevised=False):
        rows = []
        windows = [("1776-07-04", realtime_end)]
        if unrevised and not series_id.startswith("DGS"):
            raise ValueError("The unrevised-history assumption is reviewed only for daily yields")
        if series_id.startswith("DGS"):
            # FRED JSON permits at most 2,000 vintage dates per request. Daily
            # series need real-time chunks, even with a short observation range.
            first = date.fromisoformat(self.audit_series(series_id)["earliest_vintage"])
            first_vintage = first.isoformat()
            last = date.fromisoformat(realtime_end)
            if unrevised:
                # Pre-archive values come from the first archived vintage.
                last = max(last, first)
            windows = []
            while first <= last:
                stop = min(date(first.year + 5, first.month, first.day) - timedelta(days=1), last)
                windows.append((first.isoformat(), stop.isoformat()))
                first = stop + timedelta(days=1)
        for real_start, real_end in windows:
            rows.extend(self._interval(series_id, units, start, end, real_start, real_end, lag))
        if not rows:
            raise SourceUnavailable(f"No provably dated historical vintages for {series_id}")
        frame = pd.DataFrame(rows)
        if unrevised:
            frame = assume_unrevised_before(frame, first_vintage, lag)
        frame = frame.sort_values(["observation_period", "vintage_start"])
        # Remove chunk-boundary carryovers when the previous record has the same
        # value. Keep the genuinely earlier availability, including missing revisions.
        kept = []
        for _, group in frame.groupby("observation_period", sort=False):
            previous = None
            for row in group.to_dict("records"):
                equal = previous is not None and (
                    row["value"] == previous["value"]
                    or (pd.isna(row["value"]) and pd.isna(previous["value"]))
                )
                if equal and row["vintage_start_is_interval_bound"]:
                    previous["vintage_end"] = row["vintage_end"]
                else:
                    kept.append(row)
                    previous = row
        frame = pd.DataFrame(kept)
        for col in ["published_at", "available_at", "retrieved_at"]:
            frame[col] = pd.to_datetime(frame[col], utc=True)
        if frame.duplicated(["series_id", "observation_period", "vintage_start"]).any():
            raise ValueError(f"Duplicate vintage observations: {series_id}")
        return frame

    def _interval(self, series_id, units, start, end, real_start, real_end, lag):
        rows, offset = [], 0
        while True:
            response = self.get(
                "series/observations",
                series_id=series_id,
                observation_start=start,
                observation_end=end,
                realtime_start=real_start,
                realtime_end=real_end,
                output_type=1,
                limit=100000,
                offset=offset,
            )
            data = response.json()
            for x in data["observations"]:
                vintage = x["realtime_start"]
                review = self.release_reviews.get(vintage, {})
                if series_id not in review.get("series", []):
                    review = {}
                # An open-start interval is not evidence of a historical release.
                if vintage == "1776-07-04":
                    continue
                rows.append(
                    {
                        "series_id": series_id,
                        "observation_period": x["date"],
                        "value": float(x["value"]) if x["value"] != "." else float("nan"),
                        "units": units,
                        "vintage_start": vintage,
                        "vintage_start_is_interval_bound": vintage == real_start,
                        "vintage_end": x["realtime_end"],
                        "published_at": review.get("published_at"),
                        "publication_source_url": review.get("source_url"),
                        "available_at": vintage_availability(vintage, lag),
                        "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
                        "retrieved_at": response.metadata["retrieved_at"],
                        "availability_method": f"alfred_vintage_plus_{lag}_business_day_18ET",
                        "source_cache_id": response.metadata["cache_id"],
                    }
                )
            offset += len(data["observations"])
            if offset >= int(data["count"]):
                break
            if not data["observations"]:
                raise ValueError("FRED pagination ended before reported count")
        return rows


def download_observations(cache, series, start, end, realtime_end, output, unrevised=()):
    fred = Fred(cache)
    frames = []
    for sid, spec in series.items():
        frames.append(
            fred.observations(
                sid, spec["units"], start, end, realtime_end, unrevised=sid in unrevised
            )
        )
        print(f"{sid}: {len(frames[-1])} vintage records", flush=True)
    frame = pd.concat(frames, ignore_index=True)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    return frame
