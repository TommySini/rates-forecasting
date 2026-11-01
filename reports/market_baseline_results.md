# Market probabilities versus shallow boosted trees

Audited 2026-10-31 (Pacific time). This is an exploratory comparison of real
historical market prices at the existing seven-day forecast cutoff. Market
probabilities outperform the frozen trees on the small recoverable samples.
Their observed 100% classification accuracy is not an estimate of general
market reliability: history is incomplete, the shared sample has no hikes, and
nearby meetings belong to the same policy cycles.

The subsequent [gap diagnosis](market_gap_diagnosis.md) reproduces every tree
forecast and investigates missing information, weak responses to new data and
the difference between development and test retraining schedules.

The statistical baseline is now shallow boosted trees. Standalone logistic
regression is omitted from this comparison; previous experiments remain intact.
No model was retrained or tuned for these results. Market forecasts are an
external information benchmark: traders can use information absent from our
compact macro feature set, so this does not isolate an architecture effect.

## Actual coverage and matched results

The macro dataset remains 207 scheduled meetings from 2000–2025, with the existing
155/26/26 chronological split. We attempted market reconstruction for all 26
test meetings, November 2, 2022–December 10, 2025. The
[coverage table](market_baseline_runs/176b1d70bbfe/coverage.csv) records a reason
for every provider/meeting exclusion.

| Matched sample | Forecaster | Meetings | Brier ↓ | Log loss ↓ | Accuracy ↑ |
|---|---|---:|---:|---:|---:|
| Kalshi coverage | Kalshi | 10 | 0.035400 | 0.104641 | 10/10 (100%) |
| Kalshi coverage | Frozen trees | 10 | 0.441314 | 0.768635 | 7/10 (70%) |
| Shared coverage | Kalshi | 6 | 0.006417 | 0.055191 | 6/6 (100%) |
| Shared coverage | Polymarket | 6 | 0.003907 | 0.042273 | 6/6 (100%) |
| Shared coverage | Frozen trees | 6 | 0.377166 | 0.704240 | 5/6 (83.3%) |

Kalshi's ten meetings are March and September 2023; November and December 2024;
and May, June, July, September, October and December 2025. They contain five cuts,
four holds and one hike. The shared sample is the six listed 2025 meetings:
three holds followed by three cuts. Polymarket's full eligible sample equals
this intersection. Always-hold accuracy is 40% on the ten and 50% on the six.

The mean paired Brier improvement over trees is 0.405914 for Kalshi on ten
meetings, and 0.370750/0.373259 for Kalshi/Polymarket on the common six. These
are point differences, not established out-of-sample effect sizes. Neither
cohort contains two prespecified eight-meeting blocks, so bootstrap confidence
intervals are deliberately suppressed. No row-independent interval substitutes
for the missing policy-cycle evidence. The difference between the two markets
does not establish which is generally better.

For context, the archived tree Brier on all 26 meetings was 0.424813. It must not
be compared directly with a market score on six or ten different meetings.
The table above always uses the identical meeting set for each comparison.

## What accuracy and probability scores mean

Each source supplies three probabilities, not just a class label. Accuracy
selects the largest of `p_cut`, `p_hold`, and `p_hike` and counts correct labels.
The primary Brier score uses all three probabilities:

`mean_i sum_{k in {cut,hold,hike}} (p_ik - 1[y_i=k])^2`.

We do not divide by three: the range is 0–2, with lower better. Natural-log loss
is `mean_i -log(p_i,actual)`, with numerical clipping at `1e-15`. A correct
51% forecast and a correct 99% forecast have identical classification accuracy
but different probability scores. Confident mistakes incur a large log loss.

On Kalshi's ten meetings, it identifies all five cuts with no false cut calls;
trees identify three of five by argmax. The existing missed-cut-cost-2 rule
increases tree cut recall to four of five without a false cut call in this
subset. On the common six, both markets identify three of three cuts and trees
two of three under either rule. That cost-sensitive decision rule does not
alter the reported probability scores.

## One reconstructable historical snapshot

For the September 17, 2025 decision, the forecast cutoff is September 10 at
18:00 America/New_York, or **2025-09-10 22:00 UTC**. The last known official
target upper bound is 4.50%, sourced from the
[July 30 Fed statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20250730a.htm).

| Kalshi contract | Meaning after the September meeting | Bid | Ask | Midpoint | Candle end (UTC) |
|---|---|---:|---:|---:|---|
| `FED-25SEP-T4.25` | Upper target greater than 4.25% | 0.03 | 0.05 | 0.040 | September 10, 22:00 |
| `FED-25SEP-T4.50` | Upper target greater than 4.50% | 0.01 | 0.02 | 0.015 | September 10, 22:00 |

Under the documented 25-bp grid, unchanged range width and no intervening
emergency-change assumptions, these imply
`(cut, hold, hike) = (1-.040, .040-.015, .015) = (.960, .025, .015)`.
These overlapping threshold contracts are differenced, not normalized.
The hourly samples end at issuance, but the age of the standing quotes is
unknown; neither candle reports a trade close for this example.

Polymarket's reviewed September event supplies Yes-token prices of 0.1475 for
a 50+ bp cut, 0.8250 for a 25 bp cut, 0.0235 for hold and 0.0015 for a 25+ bp
hike. Their timestamps are September 10, 21:00:09–21:00:18 UTC, all before
issuance. Their sum is 0.9975. Proportional reconciliation within this reviewed
exhaustive event gives `(cut, hold, hike) = (.974937, .023559, .001504)`.
The subsequent actual decision was a cut; settlement metadata is used only to
verify that outcome, never to supply the historical forecast price.

The [quote lineage](market_baseline_runs/176b1d70bbfe/quote_lineage.parquet)
preserves each source URL, contract/token identifier, cached response identifier,
retrieval timestamp, quote timestamp, price and quality flags. Downloads took
place in 2026; retrieval time is not confused with the historical quote time.

## Sources, exclusions and assumptions

The [source/access audit](../docs/market_baseline_sources.md) records the official
documentation and exact limitations. The
[protocol](../docs/market_benchmark_plan.md) records mapping and eligibility choices
made before aggregate market scores were computed.

- **Kalshi:** public archived metadata and hourly bid/ask candle closes. Ten of
  26 meetings have both required threshold quotes within 24 hours of issuance,
  spread at most 0.10 and monotone threshold prices. Sixteen are excluded because
  a strike or quote is missing or stale; September 2024's missing current-rate
  strike is not treated as a zero probability. The raw inventory has 402 markets
  across 40 events, July 2021–July 2026, including legacy `FED-*` identifiers.
- **Polymarket:** public Gamma rules and CLOB price histories. Six reviewed
  events have compatible exhaustive outcomes and explicit rounding rules that
  preserve change direction. Older candidate events contain contradictory hike
  wording, an unmapped Other outcome, ambiguous bins or a wrong meeting date.
  They remain outside this primary mapping. Prices are reconciled only within a
  reviewed related partition when the raw sum is within 0.05 of one; observed
  sums here range from 0.9975 to 1.0015. No historical bid/ask is supplied by this
  endpoint. Exact reviewed rule hashes are pinned in the configuration.
- **CME FedWatch:** the longer-history candidate, with documented daily forecasts
  for meetings beginning in January 2015. The
  [product page](https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html)
  advertises access from $25/month, subject to the appropriate entitlement and
  licensing. There are no configured CME credentials and no CME forecasts were
  scored. Daily API publication at 01:45 UTC occurs after our prior evening's
  18:00 New York cutoff; the reporting-date convention must be confirmed and
  only an already published snapshot used. Documented intraday history starts
  November 1, 2025. No access was purchased.

Market prices can reflect risk premia, liquidity and spreads. They are probability
proxies whose calibration must be tested. Kalshi target levels can differ from
the scheduled meeting's change if an emergency move intervenes; the fixed mapping
excludes incompatible cases explicitly. There are no such intervening changes in
this eligible sample. Future cohorts must retain this check. Both platforms'
rule text is retrieved retrospectively, not a complete archive of amendments
as they stood at issuance. Current public access does not establish redistribution
rights; raw responses and generated market datasets remain local and ignored.

## Sensitivities and saved diagnostics

Where both Kalshi trade closes actually exist, only three meetings remain.
On those same three, midpoint Brier is 0.095950, trade-close Brier is 0.103533,
and tree Brier is 0.431786. Both market variants classify all three correctly.
The trade-close result is not compared to the ten-meeting midpoint aggregate.

On all six Polymarket meetings, the alternative Euclidean simplex projection
gives Brier 0.003994 versus proportional reconciliation's 0.003907; accuracy
remains 6/6. Neither method was selected by its test performance. Detailed
scores are in [matched sensitivities](market_baseline_runs/176b1d70bbfe/matched_sensitivities.csv).

![Probabilities on the six common meetings](market_baseline_runs/176b1d70bbfe/common/probabilities.png)

![Calibration with sample counts](market_baseline_runs/176b1d70bbfe/common/calibration.png)

Calibration points show only a few observations per bin and cannot establish
reliability. Separate provider plots, class-specific scores,
[cut diagnostics](market_baseline_runs/176b1d70bbfe/cut_diagnostics.csv),
[largest errors](market_baseline_runs/176b1d70bbfe/largest_errors.csv),
per-meeting probabilities and the full rule inventory are saved in the run.

## Reproduce and verify

From the project root, with the existing panel, frozen baseline and cached raw
responses present:

```sh
export UV_CACHE_DIR=.cache/uv
export MPLCONFIGDIR=.cache/matplotlib
export LOKY_MAX_CPU_COUNT=1
uv sync --frozen
uv run --frozen python scripts/run_market_baseline.py --offline
uv run --frozen python scripts/verify_market_baseline.py reports/market_baseline_runs/176b1d70bbfe
uv run --frozen pytest -q
```

Omit `--offline` to download missing public responses. No market key is needed.
Use the printed run directory if its input/code fingerprint differs. Rebuilding
the original macro panel still requires the FRED setup documented in the README.

The independent verifier checked 77 raw response hashes, reproduced raw quote
values/timestamps and the probability conversions, matched settlements to official
targets, recomputed scores and confirmed that the tree probabilities are unchanged.
Six focused market tests cover timestamp eligibility, stale data, incompatible or
incomplete outcome mapping, nonmonotone thresholds, future policy contamination,
emergency changes and exact rule versions. All 73 tests and lint passed;
plots were visually inspected. See the machine-readable
[verification record](market_baseline_runs/176b1d70bbfe/verification.json).

Initial run `806314384a53` is preserved. The correction in `062caf9a4cd7` suppresses
invalid tiny-sample uncertainty intervals and pins rule hashes; it changes no
forecast probabilities. Final offline replay `176b1d70bbfe` has a new fingerprint
because other project source files changed. Market predictions, matched tree
predictions, sensitivity predictions and quote lineage exactly equal `062caf9a4cd7`.
No modeling choices were changed after inspecting these market scores.

## Interpretation and next experiment

The available historical evidence supports making market probabilities an external
benchmark alongside the shallow trees. It does not support a claim that markets
will always be correct, that Polymarket is better than Kalshi, or that the current
model has no value outside these few meetings.

Next, repair market coverage and investigate a suitably licensed CME archive.
Then test whether macro features or an economic world model improve on the market
probabilities, with a market-only baseline on identical information timestamps and
meeting sets. A prospective forecast log is needed for genuine confirmation after
these repeated historical experiments. Keep the 207-meeting macro benchmark
independent of the much shorter market sample.
