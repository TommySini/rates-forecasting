# First snapshot review

Forecast issued 2019-07-24 18:00 America/New_York = **2019-07-24 22:00 UTC**.
Scheduled decision 2019-07-31, published 14:00 EDT = 18:00 UTC.
Detailed, machine-generated input lineage: `reports/snapshot_2019-07-31.md`.

The June 2019 payroll gain is 224,000, unemployment 3.7%, and the average gain
over three months is 170,666.67 (171,000 rounded). These agree with the original
[July 5 BLS employment release](https://www.bls.gov/news.release/archives/empsit_07052019.htm),
including the April/May revisions available then. That release was issued at
08:30 EDT. The pipeline conservatively permits its July 5 vintage on July 8 at
18:00 EDT, well before the forecast.

The June CPI vintage is July 11, eligible July 12. Headline/core year-over-year
features are 1.660866% / 2.128032%, calculated from **seasonally adjusted** index
levels in the historical information set. The [original CPI release](https://www.bls.gov/news.release/archives/cpi_07112019.htm)
reports headline year-over-year inflation using non-seasonally-adjusted levels;
its rounded 1.6% is therefore not an exact equality check for our SA feature.
No later CPI release or annual seasonal revision enters this snapshot.

Policy midpoint is 2.375%, from the [June 19 announcement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20190619a.htm).
The last scheduled action was a hold; the most recent change was December 19,
2018, 217 calendar days earlier. July 31's cut is a target only, never an input.

Treasury features use July 22 observations with a July 23 ALFRED vintage, eligible
exactly at the July 24 18:00 ET cutoff. The 2y and 10y values are 1.80% and 2.05%;
the same-date slope is 0.25 percentage points. No assumption of same-day
availability is made for financial observations.

All 19 candidate features have eligible inputs and no missing/stale flags in
this example. Claims remain audit-only for the primary experiment because of
limited early vintage coverage. This review precedes full-panel ingestion and
all model performance inspection.
