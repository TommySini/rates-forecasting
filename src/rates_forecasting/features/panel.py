from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from rates_forecasting.time import NY, at_ny, forecast_time, vintage_availability

FEATURES = [
    "policy_midpoint",
    "previous_scheduled_bps",
    "days_since_policy_change",
    "cpi_yoy",
    "core_cpi_yoy",
    "core_cpi_3m_ann",
    "payroll_1m",
    "payroll_3m_mean",
    "unemployment",
    "unemployment_3m_change",
    "claims_4w_mean",
    "claims_4w_change_pct",
    "yield_3m",
    "yield_2y",
    "yield_10y",
    "slope_10y_2y",
    "ip_3m_pct",
    "macro_max_age_days",
    "financial_max_age_days",
]


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(x) for x in value]
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def asof_observations(observations, cutoff, lag=1):
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        raise ValueError("Cutoff must be timezone-aware")
    obs = observations.copy()
    if lag != 1:
        mapped = {x: vintage_availability(x, lag) for x in obs.vintage_start.unique()}
        obs["available_at"] = pd.to_datetime(obs.vintage_start.map(mapped), utc=True)
        obs["availability_method"] = f"alfred_vintage_plus_{lag}_business_day_18ET"
    obs = obs[obs.available_at <= cutoff]
    # Resolve versions before inspecting missing values. A missing revision is not
    # permission to reuse the previous vintage of that observation.
    obs = obs.sort_values(["available_at", "vintage_start"]).drop_duplicates(
        ["series_id", "observation_period"], keep="last"
    )
    if (pd.to_datetime(obs.observation_period).dt.date > cutoff.tz_convert(NY).date()).any():
        raise ValueError("Source contains future observation periods at historical cutoff")
    return obs.sort_values(["series_id", "observation_period"])


def intervening_change(events, cutoff, target_date):
    changes = events[
        (events.scheduled_status == "unscheduled")
        & events.rate_change_bps.notna()
        & (events.rate_change_bps.abs() > 1e-8)
    ]
    uncertain = False
    for _, row in changes.iterrows():
        if pd.notna(row.decision_published_at):
            if cutoff < row.decision_published_at < at_ny(target_date, 0):
                return True
        else:
            event_date = pd.Timestamp(row.decision_date).date()
            if cutoff.tz_convert(NY).date() < event_date < pd.Timestamp(target_date).date():
                return True
            if cutoff.tz_convert(NY).date() == event_date:
                uncertain = True
    return None if uncertain else False


def make_snapshot(meeting, events, observations, series, lag=1):
    cutoff = pd.Timestamp(forecast_time(meeting["scheduled_decision_date"]))
    eligible = asof_observations(observations, cutoff, lag)
    lineage, flags = [], []
    if pd.isna(meeting["decision_published_at"]):
        flags.append("decision_intraday_time_unknown")
    values = {f: np.nan for f in FEATURES}
    latest = {}
    for sid in series:
        part = eligible[eligible.series_id == sid]
        # Daily weekends/holidays are explicit missing entries, not economic releases.
        # Preserve missing revisions for monthly/weekly latest observations.
        if series[sid]["frequency"] == "daily":
            part = part[part.value.notna()]
        if len(part):
            latest[sid] = part.iloc[-1]

    def add(name, val, inputs, formula, quality="observed"):
        if inputs and any(pd.Timestamp(x["available_at"]) > cutoff for x in inputs):
            raise ValueError(f"Future input in {name}")
        if not inputs or not np.isfinite(val):
            val = np.nan
            quality = "missing"
            flags.append("missing:" + name)
        values[name] = val
        lineage.append(
            {
                "meeting_id": meeting["meeting_id"],
                "forecast_timestamp": cutoff,
                "feature": name,
                "value": val,
                "formula": formula,
                "available_at": max((x["available_at"] for x in inputs), default=None),
                "quality": quality,
                "inputs_json": json.dumps(json_safe(inputs), allow_nan=False),
                "eligibility_reason": "All input available_at <= forecast_timestamp"
                if inputs
                else "No eligible input; explicit missing value",
            }
        )

    def source(row):
        return {
            k: row.get(k)
            for k in [
                "series_id",
                "observation_period",
                "value",
                "units",
                "vintage_start",
                "vintage_end",
                "published_at",
                "available_at",
                "source_url",
                "retrieved_at",
                "availability_method",
                "source_cache_id",
                "vintage_start_is_interval_bound",
                "publication_source_url",
            ]
        }

    def obs_inputs(sid, months=None, weeks=None):
        if sid not in latest:
            return []
        last = latest[sid]
        age = (cutoff.tz_convert(NY).date() - pd.Timestamp(last.observation_period).date()).days
        if age > series[sid]["stale_days"]:
            flags.append("stale:" + sid)
            return []
        periods = [last.observation_period]
        if months is not None:
            periods = [
                (pd.Timestamp(last.observation_period) - pd.DateOffset(months=n)).date().isoformat()
                for n in months
            ]
        if weeks is not None:
            periods = [
                (pd.Timestamp(last.observation_period) - timedelta(weeks=n)).date().isoformat()
                for n in weeks
            ]
        indexed = eligible[eligible.series_id == sid].set_index("observation_period", drop=False)
        if any(p not in indexed.index for p in periods):
            return []
        return [source(indexed.loc[p]) for p in periods]

    def calc(name, sid, operation, formula, months=None, weeks=None):
        inputs = obs_inputs(sid, months, weeks)
        val = operation([x["value"] for x in inputs]) if inputs else np.nan
        add(name, val, inputs, formula)

    history = events[
        (events.label_available_at <= cutoff) & events.policy_rate_after.notna()
    ].copy()
    history = history.sort_values("label_available_at")

    def policy_input(row, field):
        return {
            "series_id": "FOMC_ANNOUNCED_TARGET",
            "observation_period": row.decision_date,
            "value": row[field],
            "units": "percent" if field == "policy_rate_after" else "basis points",
            "vintage_start": row.decision_date,
            "vintage_end": None,
            "published_at": row.decision_published_at,
            "available_at": row.label_available_at,
            "source_url": row.source_url,
            "retrieved_at": row.source_retrieved_at,
            "availability_method": row.publication_time_method,
            "source_cache_id": row.source_cache_id,
            "before_source_url": row.get("before_source_url"),
            "target_lower_before": row.get("target_lower_before"),
            "target_upper_before": row.get("target_upper_before"),
        }

    if len(history):
        row = history.iloc[-1]
        add(
            "policy_midpoint",
            row.policy_rate_after,
            [policy_input(row, "policy_rate_after")],
            "(announced lower + announced upper) / 2; single target has equal endpoints",
        )
    previous = history[(history.scheduled_status == "scheduled") & history.rate_change_bps.notna()]
    if len(previous):
        row = previous.iloc[-1]
        add(
            "previous_scheduled_bps",
            row.rate_change_bps,
            [policy_input(row, "rate_change_bps")],
            "Last already-published scheduled decision, in basis points",
        )
    changes = history[history.rate_change_bps.notna() & (history.rate_change_bps.abs() > 1e-8)]
    if len(changes):
        row = changes.iloc[-1]
        days = (cutoff.tz_convert(NY).date() - pd.Timestamp(row.decision_date).date()).days
        add(
            "days_since_policy_change",
            days,
            [policy_input(row, "rate_change_bps")],
            "Calendar days since most recent published change, including emergency changes",
        )

    for name, sid, n, power in [
        ("cpi_yoy", "CPIAUCSL", 12, 1),
        ("core_cpi_yoy", "CPILFESL", 12, 1),
        ("core_cpi_3m_ann", "CPILFESL", 3, 4),
        ("ip_3m_pct", "INDPRO", 3, 1),
    ]:
        calc(
            name,
            sid,
            lambda v, p=power: 100 * ((v[0] / v[1]) ** p - 1),
            f"100 * ((latest / {n}-month-prior)^{power} - 1), same as-of information set",
            months=[0, n],
        )
    calc(
        "payroll_1m",
        "PAYEMS",
        lambda v: v[0] - v[1],
        "Latest minus prior month; thousands",
        months=[0, 1],
    )
    calc(
        "payroll_3m_mean",
        "PAYEMS",
        lambda v: (v[0] - v[1]) / 3,
        "(Latest minus three-month-prior)/3; thousands per month",
        months=[0, 3],
    )
    calc("unemployment", "UNRATE", lambda v: v[0], "Latest unemployment rate")
    calc(
        "unemployment_3m_change",
        "UNRATE",
        lambda v: v[0] - v[1],
        "Latest minus three-month-prior; percentage points",
        months=[0, 3],
    )
    calc(
        "claims_4w_mean",
        "ICSA",
        lambda v: np.mean(v),
        "Mean of latest four consecutive weeks",
        weeks=range(4),
    )
    calc(
        "claims_4w_change_pct",
        "ICSA",
        lambda v: 100 * (np.mean(v[:4]) / np.mean(v[4:]) - 1),
        "Percent change: latest four-week mean versus preceding four-week mean",
        weeks=range(8),
    )
    for sid, name in [("DGS3MO", "yield_3m"), ("DGS2", "yield_2y"), ("DGS10", "yield_10y")]:
        calc(name, sid, lambda v: v[0], "Latest eligible daily observation; percent")
    a, b = obs_inputs("DGS10"), obs_inputs("DGS2")
    if a and b and a[0]["observation_period"] == b[0]["observation_period"]:
        add("slope_10y_2y", a[0]["value"] - b[0]["value"], a + b, "Same-date DGS10 minus DGS2")
    else:
        add("slope_10y_2y", np.nan, [], "Require both yields on the same observation date")
    for name, frequency in [
        ("macro_max_age_days", {"monthly", "weekly"}),
        ("financial_max_age_days", {"daily"}),
    ]:
        inputs = [source(latest[s]) for s in latest if series[s]["frequency"] in frequency]
        ages = [
            (cutoff.tz_convert(NY).date() - pd.Timestamp(x["observation_period"]).date()).days
            for x in inputs
        ]
        add(
            name,
            max(ages) if ages else np.nan,
            inputs,
            "Maximum calendar age of latest eligible reference periods",
        )
    recorded = {x["feature"] for x in lineage}
    for name in FEATURES:
        if name not in recorded:
            add(name, np.nan, [], "No prior eligible policy observation")
    target_time = meeting["decision_published_at"]
    row = {
        "meeting_id": meeting["meeting_id"],
        "forecast_timestamp": cutoff,
        "target_decision_timestamp": target_time,
        "target_label_available_at": meeting["label_available_at"],
        "decision_date": meeting["decision_date"],
        "target_class": meeting["decision_class"],
        "verification_status": meeting["verification_status"],
        "data_quality_flags": json.dumps(sorted(set(flags))),
        "intervening_unscheduled_change": intervening_change(
            events, cutoff, meeting["decision_date"]
        ),
        "availability_lag_business_days": lag,
        "data_kind": "empirical",
        **values,
    }
    return row, lineage


def validate_panel(panel, lineage, meetings):
    if panel.meeting_id.duplicated().any():
        raise ValueError("Duplicate meeting at seven-day horizon")
    if not panel.target_class.isin(["cut", "hold", "hike"]).all():
        raise ValueError("Missing or invalid target")
    # Timestamp must be actual publication; unknown-time labels use a separate eligibility field.
    known = panel.target_decision_timestamp.notna()
    if not (
        panel.loc[known, "forecast_timestamp"] < panel.loc[known, "target_decision_timestamp"]
    ).all():
        raise ValueError("Forecast does not precede decision publication")
    if not (panel.forecast_timestamp < panel.target_label_available_at).all():
        raise ValueError("Forecast does not precede label availability")
    if not lineage[lineage.available_at.notna()].eval("available_at <= forecast_timestamp").all():
        raise ValueError("Future feature availability")
    expected = meetings.set_index("meeting_id").decision_class
    if not panel.target_class.eq(panel.meeting_id.map(expected)).all():
        raise ValueError("Target mismatch against verified decisions")
    for row in lineage.itertuples():
        for item in json.loads(row.inputs_json):
            if pd.Timestamp(item["available_at"]) > row.forecast_timestamp:
                raise ValueError("Future input hidden in feature lineage")
    if set(lineage.feature) != set(FEATURES) or len(lineage) != len(panel) * len(FEATURES):
        raise ValueError("Incomplete feature lineage")


def build_panel(meetings, observations, config, lag=1, only=None):
    sample = config["sample"]
    selected = meetings[
        (meetings.scheduled_status == "scheduled")
        & (meetings.decision_date >= sample["start"])
        & (meetings.decision_date <= sample["end"])
    ].copy()
    if only:
        selected = selected[selected.decision_date == only]
    bad = selected[
        selected.decision_class.isna() | (selected.verification_status != "announcement_parsed")
    ]
    if len(bad):
        raise ValueError("Unverified scheduled labels: " + ", ".join(bad.meeting_id))
    rows, lineage = [], []
    for _, meeting in selected.iterrows():
        row, sources = make_snapshot(meeting, meetings, observations, config["series"], lag)
        rows.append(row)
        lineage.extend(sources)
    if not rows:
        raise ValueError("No eligible meetings")
    panel, line = pd.DataFrame(rows), pd.DataFrame(lineage)
    # All-missing early announcement times otherwise become timezone-naive NaT.
    # Keep publication missing while retaining the UTC schema for comparisons.
    for col in ["forecast_timestamp", "target_decision_timestamp", "target_label_available_at"]:
        panel[col] = pd.to_datetime(panel[col], utc=True)
    for col in ["available_at", "forecast_timestamp"]:
        line[col] = pd.to_datetime(line[col], utc=True)
    panel["intervening_unscheduled_change"] = panel.intervening_unscheduled_change.astype("boolean")
    validate_panel(panel, line, meetings)
    return panel, line


def write_snapshot_audit(panel, lineage, path):
    row = panel.iloc[0]
    lines = [
        f"# Forecast snapshot: {row.meeting_id}",
        "",
        (
            f"Issued: **{row.forecast_timestamp.isoformat()}** "
            f"({row.forecast_timestamp.tz_convert(NY).isoformat()})."
        ),
        "",
        "Real historical inputs; no synthetic data. Target is shown for audit only and is not an input.",
        f"Target: {row.target_class}; published: {row.target_decision_timestamp}.",
        "",
        "Each input below was selected after resolving historical revisions at the cutoff.",
        "",
    ]
    for r in lineage.itertuples():
        lines += [
            f"## {r.feature}: {r.value:.6g}",
            "",
            f"Formula: {r.formula}.",
            "",
            f"Quality: {r.quality}. {r.eligibility_reason}.",
            "",
            "| Series | Value | Reference period | Vintage start/end | Available UTC | Method | Source |",
            "|---|---:|---|---|---|---|---|",
        ]
        for x in json.loads(r.inputs_json):
            lines.append(
                f"| {x['series_id']} | {x['value']} | {x['observation_period']} | "
                f"{x['vintage_start']} / {x['vintage_end']} | {x['available_at']} | "
                f"{x['availability_method']} | [source]({x['source_url']}) |"
            )
        lines.append("")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines))
