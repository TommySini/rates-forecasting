"""Fed calendar and announcement parser; unresolved labels fail closed."""

from __future__ import annotations

import re
from datetime import date
from fractions import Fraction
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import yaml
from bs4 import BeautifulSoup

from rates_forecasting.data.cache import Cache, SourceUnavailable
from rates_forecasting.time import at_ny, vintage_availability

BASE = "https://www.federalreserve.gov"
CALENDAR = BASE + "/monetarypolicy/fomccalendars.htm"
MONTHS = {
    name: n
    for n, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        1,
    )
}
MONTHS |= {k[:3]: v for k, v in list(MONTHS.items())}


def calendar_dates(title: str, year: int):
    m = re.match(r"([A-Za-z]+)(?:/([A-Za-z]+))?\s+(\d+)(?:[-–](\d+))?", title)
    if not m:
        raise ValueError(f"Unrecognized calendar heading: {title}")
    a, b, d1, d2 = m.groups()
    return (date(year, MONTHS[a], int(d1)), date(year, MONTHS[b or a], int(d2 or d1)))


def calendar_rows(response, year=None):
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    if year is not None:
        containers = [
            (h.get_text(" ", strip=True), h.find_parent("div", class_="panel"), year)
            for h in soup.select("h5")
            if re.search(r"-\s*" + str(year), h.text)
        ]
    else:
        containers = []
        for div in soup.select(".fomc-meeting"):
            heading = div.find_previous("h4").get_text(" ", strip=True)
            y = int(re.search(r"\d{4}", heading)[0])
            title = div.select_one(".fomc-meeting__month").get_text(" ", strip=True)
            title += " " + div.select_one(".fomc-meeting__date").get_text(" ", strip=True)
            containers.append((title, div, y))
    for title, container, y in containers:
        start, end = calendar_dates(title, y)
        lower = title.lower()
        status = (
            "cancelled"
            if "cancel" in lower
            else "unscheduled"
            if any(word in lower for word in ["unscheduled", "conference call", "notation vote"])
            else "scheduled"
        )
        links = []
        for a in container.find_all("a", href=True):
            label, href = a.get_text(" ", strip=True), a["href"]
            if year is not None:
                eligible = label in {"Statement", "Statement (HTML)"}
            else:
                eligible = label == "HTML" and "/pressreleases/monetary" in href
            if eligible and not href.endswith(".pdf"):
                links.append(urljoin(BASE, href))
        # Keep policy-free meetings/cancellations in inventory with explicit missing labels.
        rows.append(
            {
                "calendar_title": title,
                "meeting_start_date": start.isoformat(),
                "scheduled_decision_date": end.isoformat(),
                "scheduled_status": status,
                "source_url": links[0] if links else None,
                "calendar_source_url": response.metadata["url"],
                "calendar_retrieved_at": response.metadata["retrieved_at"],
            }
        )
    return rows


def rate_number(value):
    value = value.strip().replace("zero", "0")
    for char, frac in {"¼": " 1/4", "½": " 1/2", "¾": " 3/4"}.items():
        value = value.replace(char, frac)
    value = value.replace("-", " ")
    return float(sum(Fraction(part) for part in value.split()))


NUMBER = r"(?:zero|\d+(?:\.\d+)?(?:[- ]\d/\d)?(?:/\d)?[¼½¾]?)"


def parse_target(text):
    text = re.sub(r"[−‑–]", "-", re.sub(r"\s+", " ", text.replace("\xa0", " ")))
    range_pattern = (
        r"target range for the federal funds rate\s+(?:by [^,.;]{1,40},?\s+)?(?:at|to|of)\s+("
        + NUMBER
        + r")\s+to\s+("
        + NUMBER
        + r")\s+percent"
    )
    m = re.search(range_pattern, text, re.IGNORECASE)
    if m:
        return rate_number(m[1]), rate_number(m[2]), "range", m[0]
    m = re.search(
        r"federal funds rate in a target range of (" + NUMBER + r") to (" + NUMBER + r") percent",
        text,
        re.IGNORECASE,
    )
    if m:
        return rate_number(m[1]), rate_number(m[2]), "range", m[0]
    m = re.search(
        r"current ("
        + NUMBER
        + r") to ("
        + NUMBER
        + r") percent target range for the federal funds rate",
        text,
        re.IGNORECASE,
    )
    if m:
        return rate_number(m[1]), rate_number(m[2]), "range", m[0]
    if "target range" in text.lower():
        raise ValueError("Unrecognized range wording; refusing single-rate fallback")
    # Match the decision paragraph before any dissent. Never parse effective funds rates.
    single = (
        r"(?:target for the federal funds rate|federal funds rate(?: target)?)"
        r"[^.;]{0,110}?\b(?:to|at|of)\s+(?:around |about )?(" + NUMBER + r")\s+percent"
    )
    m = re.search(single, text, re.IGNORECASE)
    if m:
        x = rate_number(m[1])
        return x, x, "single", m[0]
    raise ValueError("No unambiguous announced policy target parsed")


def decision_label(before_lower, before_upper, after_lower, after_upper):
    vals = [before_lower, before_upper, after_lower, after_upper]
    if not all(np.isfinite(v) for v in vals):
        return np.nan, None
    if before_lower > before_upper or after_lower > after_upper:
        raise ValueError("Inverted target range")
    # Midpoint also handles the 2008 single-target to range transition.
    bps = 100 * ((after_lower + after_upper - before_lower - before_upper) / 2)
    return bps, "hike" if bps > 1e-8 else "cut" if bps < -1e-8 else "hold"


def parse_statement(response):
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    # Prefer the actual release header. Some official URL slugs contain typos:
    # monetary20070618a.htm is the June 28, 2007 announcement.
    matches = re.findall(r"(?:19|20)\d{6}", response.metadata["url"])
    if not matches:
        raise ValueError("No announcement date encoded in source URL")
    d = pd.Timestamp(matches[0]).date()
    date_method = "url_date_fallback"
    header = soup.select_one(".article__time")
    legacy = re.search(r"Release Date:\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})", text)
    if header is not None:
        d = pd.Timestamp(header.get_text(" ", strip=True)).date()
        date_method = "announcement_date_header"
    elif legacy:
        d = pd.Timestamp(legacy[1]).date()
        date_method = "announcement_date_header"
    try:
        low, high, regime, excerpt = parse_target(text)
    except ValueError:
        overrides = yaml.safe_load(Path("configs/announcement_reviews.yaml").read_text())
        review = overrides.get(d.isoformat())
        if review is None or review.get("target_lower_after") is None:
            raise
        if review["source_url"] != response.metadata["url"]:
            raise ValueError("Review source URL does not match announcement") from None
        low, high = review["target_lower_after"], review["target_upper_after"]
        regime, excerpt = "single" if low == high else "range", review["evidence"]
    m = re.search(r"For release at(\s*\d{1,2}):(\d{2})\s*([ap])\.?m\.?", text, re.IGNORECASE)
    published = None
    if m:
        hour = int(m[1]) % 12 + (12 if m[3].lower() == "p" else 0)
        published = at_ny(d, hour, int(m[2]))
    effective = re.search(
        r"effective\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        text,
    )
    effective_date = (
        date(int(effective[3]), MONTHS[effective[1]], int(effective[2])).isoformat()
        if effective
        else None
    )
    return {
        "decision_date": d.isoformat(),
        "announcement_date_method": date_method,
        "decision_published_at": published,
        "label_available_at": published or vintage_availability(d.isoformat()),
        "publication_time_method": "stated_release_time" if published else "next_business_day_18ET",
        "policy_effective_date": effective_date,
        "target_lower_after": low,
        "target_upper_after": high,
        "policy_rate_after": (low + high) / 2,
        "target_regime": regime,
        "verification_excerpt": excerpt,
        "source_retrieved_at": response.metadata["retrieved_at"],
        "source_cache_id": response.metadata["cache_id"],
    }


def build_meetings(cache: Cache, start=1994, end=2025):
    inventory = []
    for year in range(start, min(end, 2020) + 1):
        url = f"{BASE}/monetarypolicy/fomchistorical{year}.htm"
        inventory.extend(calendar_rows(cache.get(url), year))
        print(f"Calendar {year} cached", flush=True)
    if end >= 2021:
        inventory.extend(
            r
            for r in calendar_rows(cache.get(CALENDAR))
            if max(start, 2021) <= int(r["scheduled_decision_date"][:4]) <= end
        )
    rows = []
    reviews = yaml.safe_load(Path("configs/announcement_reviews.yaml").read_text())
    for row in inventory:
        row = row.copy()
        if row["scheduled_decision_date"] == "2003-09-15":
            row["scheduled_status"] = "non_policy_session"
            row["classification_source_url"] = BASE + "/fomc/minutes/20030812.htm"
        row["verification_status"] = "no_policy_statement"
        if row["source_url"] and row["scheduled_status"] != "cancelled":
            try:
                row.update(parse_statement(cache.get(row["source_url"])))
                row["verification_status"] = "announcement_parsed"
            except (ValueError, SourceUnavailable) as exc:
                row["verification_status"] = "unresolved"
                row["verification_error"] = str(exc)
                dates = re.findall(r"(?:19|20)\d{6}", row["source_url"])
                if dates:
                    row["decision_date"] = pd.Timestamp(dates[0]).date().isoformat()
                    review = reviews.get(row["decision_date"], {})
                    if (
                        review.get("non_target_action")
                        and review["source_url"] == row["source_url"]
                    ):
                        row["verification_status"] = "non_target_statement_reviewed"
                        row["verification_excerpt"] = review["evidence"]
        row.setdefault("decision_date", row["scheduled_decision_date"])
        row["meeting_id"] = "FOMC-" + row["decision_date"]
        rows.append(row)
    frame = pd.DataFrame(rows).sort_values(["decision_date", "meeting_start_date"])
    if frame.meeting_id.duplicated().any():
        raise ValueError("Duplicate meeting IDs in calendar inventory")
    prior = None
    for idx, row in frame.iterrows():
        if row.verification_status != "announcement_parsed":
            continue
        if prior is not None:
            for attr in ["policy_rate", "target_lower", "target_upper"]:
                frame.loc[idx, attr + "_before"] = prior[attr + "_after"]
            bps, label = decision_label(
                prior["target_lower_after"],
                prior["target_upper_after"],
                row.target_lower_after,
                row.target_upper_after,
            )
            frame.loc[idx, "rate_change_bps"] = bps
            frame.loc[idx, "decision_class"] = label
            frame.loc[idx, "before_source_url"] = prior["source_url"]
        prior = row
    for col in [
        "decision_published_at",
        "label_available_at",
        "source_retrieved_at",
        "calendar_retrieved_at",
    ]:
        frame[col] = pd.to_datetime(frame[col], utc=True)
    Path("data/interim").mkdir(parents=True, exist_ok=True)
    frame.to_parquet("data/interim/meeting_inventory.parquet", index=False)
    return frame
