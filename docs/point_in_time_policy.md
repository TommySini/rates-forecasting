# Point-in-time policy, version 1

Seven calendar days before the **scheduled decision date**, issue at 18:00
America/New_York. If that date is not a US federal business day, roll back to the
preceding one, retaining 18:00 local time. Business days exclude weekends and the
pandas `USFederalHolidayCalendar`, including Juneteenth from 2021; this is not an
NYSE calendar. Historical ad hoc closures are not separately modeled. Convert
the wall time using IANA timezone rules, then store UTC-aware timestamps.

`observation_period` describes the economic reference period, never availability.
`published_at` is an actual source publication timestamp, or null. `available_at`
is the earliest permitted use. `retrieved_at` records our much later download.
An ALFRED vintage date is a date, not an intraday release timestamp. Uniformly
permit it at 18:00 New York time on the **following federal business day**.
The predeclared sensitivity uses two business days. This rule also covers yields.
For the two manually checked July 2019 BLS releases, exact publication times and
their source URLs are also stored from `configs/release_timestamp_reviews.yaml`;
the conservative availability convention remains unchanged.

Select every observation's most recent **eligible** version at each forecast.
Compute growth from these selected versions. Do not join to today's revised
history, backfill from future periods, or reuse an old value when a newer eligible
revision explicitly marks that period missing. Because availability is delayed,
the last eligible vintage remains usable until its replacement becomes eligible;
do not discard it solely because its vendor `vintage_end` has passed. Vendor
interval endpoints are inclusive dates and may be clipped to the requested window.

Daily source intervals are downloaded in five-year chunks because FRED JSON
limits a request to 2,000 vintages. Identical-value carryovers at chunk boundaries
are merged with the prior interval. A boundary without an earlier record is
explicitly marked as an interval bound and receives conservative availability at
that bound plus the lag. It is never treated as proof of earlier release. Initial
open-start intervals at 1776-07-04 are rejected as unproven availability.

All growth comparisons require exact monthly/weekly reference periods. Missing
periods stay missing. Financial slope inputs must share the same observation
date. Daily missing weekend/holiday entries are not releases. Staleness limits
are 100 calendar days from the reference-period date for monthly observations,
28 for weekly claims, and 10 for yields. Stale features become null and are
flagged; no row is dropped because a model might find it difficult. Age features
describe carried observations without pretending they are new releases.

Policy features use only already-available announcements, including intermeeting
actions. Known announcement times are read from the release header. A web page's
last-update time is never used. Unknown publication times remain null, with
`label_available_at` set to the next business day at 18:00 ET. Actual decision
dates are read from the announcement header (official URL slugs can be wrong).
Unknown effective dates remain null; an announcement and its implementation are
distinct. The model's policy level is the latest **announced** target midpoint.

Targets compare the immediately preceding announced target with the target in
the scheduled meeting's announcement. Single targets have equal endpoints;
ranges use their midpoint. Therefore the December 2008 transition from 1% to
0–0.25% is a cut with a midpoint change of −87.5 bp (not a claimed quoted step
size). The effective funds rate is never an input for constructing labels.

Emergency changes between forecast issuance and decision remain separate events
and get an outcome-side flag, excluded from model features. Unknown event times
on the forecast date yield an unknown flag. All scored scheduled events remain
in the primary evaluation. Report excluding 2020, 2020 alone, and with/without
intervening changes. Cancelled March 18, 2020 has an issued forecast convention
but no realized scheduled decision: retain it in the exclusions ledger with the
March 15 intervention flagged; do not label cancellation as a hold.

Training rows require both an earlier forecast and a label available strictly
before the new issuance. Imputation and scaling live inside each fitted model.
Development selects among two logistic and two tree settings. Holdout predictions
retrain on expanding history, including previously observed holdout labels, with
fixed modeling choices. Availability sensitivity reuses primary selected settings.

Raw bytes, public request parameters, retrieval timestamp, response hash and cache
ID are retained. Cache keys and metadata exclude credentials. Every feature
records all contributing values, periods, versions, timestamps and sources in
separate Parquet lineage. The pipeline fails on duplicate meetings, mismatched
targets, future inputs, or incomplete lineage.

Limitations: the calendar is the Fed's retrospective archive, not an independently
versioned schedule at each issuance. ALFRED metadata can have historical errors;
a conservative lag mitigates intraday ambiguity but cannot certify perfect
archive completeness. Original-release spot checks and sensitivity remain necessary.
