# Extended 2000–2025 history: specification and source review

Specified on 2026-10-30 before examining this experiment's performance, after the
user requested using the already labeled 2000–2005 meetings. All historical
results remain exploratory because earlier runs examined overlapping test dates.

## Cohort and availability

The inventory verifies 48 scheduled decisions in 2000–2005: 10 cuts, 16 hikes,
22 holds. Eight cuts occur in 2001, one in 2002 and one in 2003. These add one
concentrated easing period, not ten independent policy-cycle experiments.

The resulting cohort contains 207 meetings: 27 cuts, 40 hikes and 140 holds.
Keep the user's 75% / 12.5% / 12.5% chronological split, rounded 155/26/26:

| Split | Dates | Cuts | Holds | Hikes |
|---|---|---:|---:|---:|
| Training | 2000-02-02–2019-05-01 | 18 | 108 | 29 |
| Development | 2019-06-19–2022-09-21 | 3 | 18 | 5 |
| Test | 2022-11-02–2025-12-10 | 6 | 14 | 6 |

The 2001 cycle enters **training**, not development. Development gains the three
2019 cuts because the larger cohort moves the percentage boundaries earlier.
Do not move 2001 into development after training on later years.

The existing Treasury vintage audit begins June 2005. We do not fill older yields
with today's history or retain yield missingness as a proxy for early eras.
This experiment uses 12 policy/macro features throughout 2000–2025: announced
target midpoint, previous scheduled change, time since last policy change,
headline/core CPI growth, core CPI three-month annualized growth, monthly and
three-month payroll changes, unemployment level/change, industrial-production
growth, and macro reference age. Claims, yields, yield slope and financial age
are excluded throughout. The original 17-feature benchmark is preserved.

Download CPIAUCSL, CPILFESL, PAYEMS, UNRATE and INDPRO using full real-time
intervals, observation history beginning 1998 for warmup, and real-time end
2025-12-31. Current revised histories never substitute for historical vintages.
Unknown release times retain vintage + one federal business day at 18:00 New
York. UTC timestamps, revisions, staleness and missingness rules are unchanged.
Separate `extended_2000` data/report directories preserve original artifacts.

## Early-period snapshot review

Reconstruct January 31, 2001 at the January 24, 2001 18:00 New York cutoff.
The [January 3 emergency statement](https://www.federalreserve.gov/boarddocs/press/general/2001/20010103/)
lowered the announced target from 6.5% to 6.0%; the [January 31 scheduled statement](https://www.federalreserve.gov/boarddocs/press/general/2001/20010131/)
then lowered it from 6.0% to 5.5%. The scheduled label is therefore -50 basis
points, not the combined January reduction. The emergency move predates issuance.

The original [January 5, 2001 BLS employment release](https://www.bls.gov/news.release/History/empsit_01052001.txt)
reports December payroll growth of 105,000, unemployment of 4.0%, and a rounded
three-month payroll gain of 77,000. Its embargo time was 08:30 EST. Check these
against ALFRED's contemporaneous snapshot before scaling the extended panel.
The machine-readable snapshot and feature-by-feature audit are saved separately.

Review passed before the full panel build: all 12 included inputs are present.
The cutoff is 2001-01-24 23:00 UTC, target midpoint 6.0%, previous scheduled
change 0 bp, and time since the January 3 change 21 days. Payroll growth is
105,000; the three-month mean is 76,666.67 (matching BLS's rounded 77,000);
unemployment is 4.0%. The verified BLS publication time is stored separately
from the conservative January 8, 2001 23:00 UTC availability time. CPI and
industrial-production inputs become eligible January 18 at 23:00 UTC. Every
feature input is eligible before the January 24 cutoff. Excluded claims/yield
columns remain explicitly missing and do not enter the models.

## Prespecified comparisons

Keep the prior 55-candidate grid, four chronological development blocks, cut
component weight 2, missed-cut decision cost 2, and all probability metrics.
No new hyperparameter ranges are chosen after looking at these scores.

1. Expanded history: all 207 meetings, 155 initial training rows.
2. Matched 2006-start control: identical 12 features and identical development/test
   meetings, but omit the 48 early training rows. Tune the same 55 candidates on
   the same validation blocks. This tests the expanded-history procedure with
   equal feature information and tuning budget; settings may differ by cohort.
3. 2001 concentration sensitivity: omit the eight 2001 scheduled decisions from
   training examples, retain all real historical policy information in later
   feature snapshots, and retain the expanded model's selected settings and
   development/test boundaries. Do not claim this produces independent episodes.

The sensitivity retains 199 observations and 147 initial training rows. It
measures dependence on that training year with fixed settings; it is not a
causal estimate of the 2001 cycle's effect. Save per-meeting predictions and
paired block-bootstrap differences on the same 26 test meetings. The existing
eight-meeting blocks do not turn the small number of policy cycles into a large
independent sample. Report class/year counts and the 2001 sensitivity explicitly.

## Commands

```sh
uv run --frozen rates snapshot --config configs/extended_2000.yaml
# Review reports/extended_2000/snapshot_2001-01-31.md before the next command.
uv run --frozen rates panel --config configs/extended_2000.yaml
uv run --frozen python scripts/compare_history.py
uv run --frozen python scripts/verify_outputs.py
```

The snapshot/panel commands use FRED_API_KEY locally for initial downloads; add
`--offline` for cached replay. Use the README's UV_CACHE_DIR, MPLCONFIGDIR and
LOKY_MAX_CPU_COUNT environment settings. The comparison script needs only local
data and does not access the network.
