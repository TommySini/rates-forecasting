"""Score frozen model forecasts on exactly the meetings with market probabilities.

No refitting: model forecasts come from the yields comparison run and market
forecasts from the market baseline run. Each table uses one identical meeting set.
"""

import sys
from pathlib import Path

import pandas as pd

from rates_forecasting.evaluation.metrics import summary

model_run = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/policy_model_runs/24f35e51a919")
market_run = Path(sys.argv[2] if len(sys.argv) > 2 else "reports/market_baseline_runs/176b1d70bbfe")
models = pd.read_parquet(model_run / "predictions.parquet")
prefix = f"reports/market_overlap_{model_run.name}"
markets = pd.read_parquet(market_run / "market_predictions.parquet")


def blackout_start(meeting_start):
    """Midnight New York on the second Saturday before the meeting begins.

    FOMC external-communications policy; its holiday-Friday exception is not
    applied here because only the ordering relative to issuance is checked.
    """
    day = pd.Timestamp(meeting_start) - pd.Timedelta(days=1)
    saturdays = 0
    while saturdays < 2:
        saturdays += day.weekday() == 5
        day -= pd.Timedelta(days=1)
    return (day + pd.Timedelta(days=1)).tz_localize("America/New_York").tz_convert("UTC")


# Both forecasts must be made at the same moment: every market quote at or before
# the model's seven-day issuance time, which falls inside the Fed's blackout.
quotes = pd.read_parquet(market_run / "quote_lineage.parquet").merge(
    markets[["meeting_id", "model_name"]].rename(columns={"model_name": "provider"}),
    on=["meeting_id", "provider"],
)
quotes = quotes[quotes.status == "available"]
inventory = pd.read_parquet("data/interim/meeting_inventory.parquet").set_index("meeting_id")
issued = models.groupby("meeting_id").forecast_timestamp.first()
timing = quotes.groupby(["meeting_id", "provider"], as_index=False).agg(
    market_cutoff=("forecast_timestamp", "first"),
    latest_quote=("quote_timestamp", "max"),
    earliest_quote=("quote_timestamp", "min"),
    quotes=("contract_id", "size"),
)
timing["model_issuance"] = timing.meeting_id.map(issued)
timing["blackout_start"] = timing.meeting_id.map(
    lambda m: blackout_start(inventory.loc[m, "meeting_start_date"])
)
timing["decision_date"] = timing.meeting_id.map(inventory.decision_date)
timing["hours_quote_before_issuance"] = (
    timing.model_issuance - timing.latest_quote
).dt.total_seconds() / 3600
timing["days_issuance_after_blackout_start"] = (
    timing.model_issuance - timing.blackout_start
).dt.total_seconds() / 86400
assert (timing.market_cutoff == timing.model_issuance).all(), "different issuance times"
assert (timing.latest_quote <= timing.model_issuance).all(), "market quote after issuance"
assert (timing.blackout_start < timing.model_issuance).all(), "issuance before blackout"
timing.to_csv(f"{prefix}_timing.csv", index=False)

columns = ["meeting_id", "decision_date", "actual_class", "model_name"]
columns += ["p_cut", "p_hold", "p_hike", "brier", "log_loss", "correct"]
combined = pd.concat([models[columns], markets[columns]], ignore_index=True)

kalshi = set(markets.loc[markets.model_name == "kalshi", "meeting_id"])
polymarket = set(markets.loc[markets.model_name == "polymarket", "meeting_id"])
rows = []
for cohort, meetings, sources in [
    ("kalshi_coverage", kalshi, ["kalshi"]),
    ("shared_coverage", kalshi & polymarket, ["kalshi", "polymarket"]),
]:
    frame = combined[combined.meeting_id.isin(meetings)]
    frame = frame[frame.model_name.isin([*sources, *models.model_name.unique()])]
    table = summary(frame)
    table.insert(0, "cohort", cohort)
    rows.append(table)
result = pd.concat(rows, ignore_index=True)
result.to_csv(f"{prefix}_comparison.csv", index=False)

detail = combined[combined.meeting_id.isin(kalshi)].copy()
detail["p_actual"] = detail.apply(lambda r: r["p_" + r.actual_class], axis=1)
wide = detail.pivot(
    index=["decision_date", "actual_class"], columns="model_name", values="p_actual"
)
wide.to_csv(f"{prefix}_meetings.csv")
print(result.round(4).to_string(index=False))
print("\nProbability assigned to the actual outcome:")
print(wide.round(2).to_string())
