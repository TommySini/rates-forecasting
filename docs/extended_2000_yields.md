# Extended 2000–2025 panel with Treasury yields: specification

Recorded 2026-10-31 before downloading the pre-2005 yield history or computing
any score with it. The user asked to restore yields after the structured-policy
results showed the remaining problem is turning points. Results are exploratory:
the 26 test meetings were examined in earlier experiments.

## Data assumption

ALFRED's archive of daily Treasury yields (DGS3MO, DGS2, DGS10) starts on
2005-06-28, so the `extended_2000` panel excluded yields entirely. In the cached
2005–2025 archive, 0.05% of DGS10 and 0.02% of DGS2/DGS3MO daily observations
ever take a second value; the monthly macro series are revised 56–99% of the time.

For these three series only, values dated before 2005-06-28 are read from the
first archived vintage and become available on their **observation date plus one
federal business day at 18:00 New York**, the rule already used for unknown
release times. Rows keep the original ALFRED vintage in `alfred_vintage_start`
and are labeled `assumed_unrevised_daily_obs_plus_1_business_day_18ET`. From
2005-06-28 onward, genuine ALFRED vintages apply unchanged, including any later
revisions of pre-archive dates. The assumption is refused in code for any
non-daily series.

New dataset `extended_2000_yields` (config `configs/extended_2000_yields.yaml`):
the same 207 meetings, labels, macro vintages and split (155/26/26), plus the
three yields, the 10y–2y slope and financial data age: 17 model features.
Original `extended_2000` artifacts are untouched.

## Snapshot review before scaling

Reconstruct January 31, 2001 (cutoff January 24, 2001, 18:00 New York). All 17
features must be present, yields must come from January 23, 2001 or earlier, and
the 3-month, 2-year and 10-year values must match the Federal Reserve's original
H.15 release for that week. Macro values must equal the reviewed `extended_2000`
snapshot.

## Comparisons fixed in advance

A. **Statistical baseline.** The unchanged pipeline (`rates evaluate`) with the
   existing 55-candidate grid and four development blocks, on 17 features. Report
   trees with yields (`trees_17f`) against the frozen 12-feature trees
   (`trees_12f`). Logistic regression is produced by the pipeline but, following
   the user's decision, is not part of the comparison.

B. **Small ordered models** (untuned; weak N(0, 2²) weights, same lower-bound rule
   and threshold priors as the structured-policy experiment):
   - `momentum_ordered`: previous scheduled move / 25 bp only (3 parameters). It
     registers the post-hoc benchmark; it uses no yields.
   - `market_ordered`: previous move plus the 3-month bill spread
     (`yield_3m − policy midpoint`) and the 2-year spread (`yield_2y − policy
     midpoint`) (5 parameters). Negative spreads mean markets price lower rates.
   - `market_ordered_post2005`: identical, trained only on meetings from 2006,
     so no assumed pre-archive yield enters training. Sensitivity only.

   Frozen references: `trees_17f`, `trees_12f`, and the 12-feature
   `taylor_ordered` from run `14f31bd8c716`.

All forecasts refit at each test meeting on labels available before issuance.
Report all 26 meetings and the **14 after-hold meetings**, those whose previous
scheduled decision was a hold (defined at issuance, not from the outcome; 11
holds, the July 2023 hike and the September 2024 and September 2025 cuts).

## Interpretation rules

- "Yields help the small model" requires `market_ordered` to have lower Brier
  than `momentum_ordered` on all 26 meetings **and** on the 14 after-hold
  meetings. Three moves in that subset make any conclusion very weak.
- "Yields help trees" requires `trees_17f` below `trees_12f` on all 26 meetings.
- If `market_ordered_post2005` loses most of the gain, the result leans on the
  pre-archive assumption and must be reported that way.
- Intervals are descriptive. No change after seeing test scores.

## Snapshot review outcome

Passed before the full panel build. At the 2001-01-24 23:00 UTC cutoff, all 17
features are present. Yields come from 2001-01-23 and become available exactly
at the cutoff: 3-month 5.24%, 2-year 4.82%, 10-year 5.30%, identical to the
[original H.15 release of January 29, 2001](https://www.federalreserve.gov/releases/h15/20010129/).
Payroll growth 105,000, three-month mean 76,666.67 and unemployment 4.0% equal
the reviewed `extended_2000` snapshot.

The full panel keeps all 12 shared features and every label identical to
`extended_2000` and has no input available after issuance. Five meetings
(August 2005–January 2006) have missing yields: from July 2005 to February 2006
ALFRED archived these series only weekly, so the latest archived value is older
than the 10-day staleness limit. They remain explicit missing values, as
specified; they are not filled with the unrevised-history assumption.
