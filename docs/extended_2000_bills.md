# Adding the 1-month Treasury yield: specification

Recorded 2026-10-31 before downloading the series or computing any score with
it. The user chose the free 1-month bill as the first longer-history market
signal. Results are exploratory: the 26 test meetings were examined before.

## Data

Add DGS1MO (1-month Treasury constant maturity, H.15; same family and quoting
basis as DGS3MO, DGS2 and DGS10) as feature `yield_1m`, in a new dataset
`extended_2000_bills` (`configs/extended_2000_bills.yaml`). Everything else is
the `extended_2000_yields` dataset: same 207 meetings, labels, split and features.
DGS1MO is added to the reviewed unrevised-daily-yield list: values dated before
its first ALFRED vintage become available on their observation date plus one
federal business day, labeled in lineage. The series begins 2001-07-31, so the
roughly 12 meetings from February 2000 to June 2001 have explicit missing values.

`yield_1m` is an optional feature: it exists only in datasets that configure
DGS1MO, so earlier panels, models and verifications are unchanged.

## Snapshot review before scaling

The January 2001 snapshot predates the series, so the review uses the October 2,
2001 meeting (cutoff September 25, 2001, 18:00 New York; after the September 17
emergency cut). All configured features must be present; the 1-month, 3-month,
2-year and 10-year values must match the Federal Reserve's original H.15 release
for that week; the policy midpoint must reflect the September 17 cut.

## Comparison fixed in advance

Same protocol as the yields experiment (untuned ordered models, weak N(0, 2²)
weights, lower-bound rule, refit at each test meeting on available labels):

- `market_1m_ordered`: previous move / 25 bp, 1-month spread (`yield_1m − policy
  midpoint`), 3-month spread and 2-year spread (6 parameters). Missing 1-month
  values before August 2001 use the training median, as for any missing input.
- `market_1m_ordered_post2005`: identical, trained on meetings from 2006 only.

Frozen references: `market_ordered` (3-month and 2-year spreads) and
`momentum_ordered` from run `24f35e51a919`, and `trees_17f`. Report all 26 test
meetings, the 14 after-hold meetings, and the Kalshi/Polymarket meetings with
the timing check.

## Interpretation rules

- "The 1-month bill helps" requires `market_1m_ordered` to have lower Brier than
  `market_ordered` on all 26 meetings **and** on the 14 after-hold meetings.
- The 1-month and 3-month spreads are strongly correlated; individual weights
  are not interpreted as separate effects.
- Intervals are descriptive. No change after seeing test scores.
