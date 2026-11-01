# 1-month Treasury yield: computed results

Specification: [docs/extended_2000_bills.md](../docs/extended_2000_bills.md),
recorded before the series was downloaded. Run
[`16e2b48fea80`](policy_model_runs/16e2b48fea80/complete.json); verification passed.
Exploratory: these test years were used before.

## Headline

**The 1-month yield does not help.** Adding it to the market model makes the
score worse on all 26 test meetings and changes nothing after holds. The
registered condition is not met. Nearly all of the loss comes from one meeting
distorted by the 2023 debt-ceiling standoff.

## Data check

The October 2, 2001 snapshot (cutoff September 25, 2001) reproduces the
[original H.15 release of October 1, 2001](https://www.federalreserve.gov/releases/h15/20011001/)
exactly for September 24: 1-month 2.38%, 3-month 2.38%, 2-year 2.94%, 10-year
4.73%. The policy midpoint is 3.0%, after the September 17 emergency cut. The full
panel keeps every base feature and label identical to `extended_2000_yields`, and
no input is available after issuance. `yield_1m` is missing for 17 meetings: the
12 before the series began (February 2000–June 2001) and the same five weekly-
archive meetings of August 2005–January 2006.

## Results on the same 26 test meetings

| Model | Brier, all 26 | Brier, 14 after a hold |
|---|---:|---:|
| `market_ordered` (3-month + 2-year spreads, frozen) | **0.252** | **0.198** |
| `market_1m_ordered` (+ 1-month spread) | 0.285 | 0.200 |
| `market_1m_ordered_post2005` (sensitivity) | 0.330 | 0.207 |
| `momentum_ordered` (frozen) | 0.343 | 0.362 |
| `trees_17f` (frozen) | 0.432 | 0.422 |

Paired Brier, `market_ordered` − `market_1m_ordered`: −0.034 [−0.093, −0.003] on
all 26; −0.001 [−0.004, +0.002] after a hold.

On the Kalshi meetings the picture is the same: 0.333 with the 1-month spread
versus 0.320 without, against 0.035 for Kalshi
([comparison](market_overlap_16e2b48fea80_comparison.csv),
[timing check](market_overlap_16e2b48fea80_timing.csv)).

## Why

On May 3, 2023 the Fed hiked. At issuance, during the debt-ceiling standoff, the
1-month yield was 1.34 points below the policy midpoint because bills maturing
before the expected default date were in heavy demand. The model read that as a
priced cut and gave the hike much less probability; that meeting alone accounts
for a Brier difference of 0.72 (0.028 of the 26-meeting average). Elsewhere the
two models differ by at most about 0.05 per meeting. The 1-month bill measures
expected policy plus safety and supply effects, and the latter can dominate.

## Note on intervals

The interval for `momentum_ordered − market_ordered`, identical forecasts in both
runs, was [+0.001, +0.189] in the yields run and is [−0.007, +0.195] here, because
the bootstrap draws depend on which models are compared. Intervals that barely
exclude zero should not be read as firm evidence.

## Consequence

Keep `market_ordered` as the anchor. Bill yields add little beyond the 3-month
bill and carry debt-ceiling and flight-to-safety noise; fed funds futures, the
instrument designed to price the fed funds rate, remain the next proper source
([source review](../docs/market_expectation_sources.md)).
