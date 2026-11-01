# Diagnosis of the market/tree forecast gap

Investigated 2026-10-31. This is a post-hoc audit of already inspected historical
results. Existing forecasts and model settings remain unchanged. Evidence is in
[market_gap-1b24215713c3](diagnostic_runs/market_gap-1b24215713c3/complete.json).

The trees underreact in important episodes and lack information available to
market participants. A concrete design issue also emerged: development model
selection and test forecasts use different retraining schedules. Matching those
schedules changes the development winner. That does not yet establish how much
of the market gap a replacement would close.

## Checks and findings

| Possible explanation | Check | Finding |
|---|---|---|
| Incorrect class order or stale fitted model | Refit all 26 forecasts; independently reconstruct probabilities from tree leaf contributions | All match saved probabilities exactly; estimator cut/hike/hold order is correctly mapped to cut/hold/hike |
| Market timestamps or outcome mapping wrong | Rerun independent verifier on 77 raw response hashes, quotes, mappings, settlements and scores | Passes; retained historical samples are at/before issuance |
| September jobs data absent | Compare lineage with dated BLS release | Correct +22,000 payrolls and 4.3% unemployment were already inputs |
| Midpoints artificially improve Kalshi | Maximize Brier within recorded bid/ask bounds, preserving monotone thresholds | Ten-meeting mean increases from .0354 to at most .0411, still far below trees' .4413 |
| Fitted classifier barely responds | Exact September 2025 decomposition | Cut probability starts at 11.8% and ends at 12.4% |
| Tuning does not match forecast procedure | Repeat the same 48 tree candidates with per-meeting development refits | Preferred settings change; comparable development Brier improves from .296 to .258 |
| Adding yields resolves the problem | Compare previously saved yield-model forecasts on identical meetings | Improves some forecasts but leaves a large gap |

No score, class-order, refit or cutoff error was found in the audited paths.
This does not establish that every source or implementation detail is correct.
Historical market rule amendments and actual standing-quote age remain
unverified. Quote-spread bounds are not confidence intervals or executable returns.

## September 2025: correct inputs, weak response

The September 17 decision's issuance is September 10 at 18:00 New York, 22:00 UTC.
There is no intervening emergency change in this case.

| Input | Value | Reference period | Permitted availability, UTC |
|---|---:|---|---|
| Policy midpoint | 4.375% | July 30 decision | July 30, 18:00 |
| Previous scheduled move | 0 bp | July 30 decision | July 30, 18:00 |
| Days since last change | 266 | December 18, 2024 change | Already known |
| Payroll growth | +22,000 | August 2025 | September 8, 22:00 |
| Three-month payroll growth mean | +29,333/month | June–August 2025 | September 8, 22:00 |
| Unemployment | 4.3% | August 2025 | September 8, 22:00 |
| Three-month unemployment change | +0.1 percentage point | May–August 2025 | September 8, 22:00 |
| Headline CPI annual growth | 2.732% | July 2025, seasonally adjusted | August 13, 22:00 |
| Core CPI annual growth | 3.049% | July 2025, seasonally adjusted | August 13, 22:00 |

The [BLS release](https://www.bls.gov/news.release/archives/empsit_09052025.htm)
was published September 5 at 08:30 Eastern and reports the same payroll and
unemployment readings. Our conservative rule admits them the following business
day, September 8 at 18:00 Eastern. Publication lag does not explain this miss.
Reference-period age, such as July CPI, is distinct from release age.

Training expands as labels become known. By this forecast it contains 204
meetings: 140 holds, 40 hikes and 24 cuts. Of the cuts, 17 follow a scheduled
cut and only seven follow a scheduled hold. These are not seven independent
cycles; emergency moves can also occur between scheduled meetings.

The selected model uses depth-one trees, 40 boosting rounds, learning rate .03,
minimum leaf size 10 and L2 regularization 1. Each tree has one split, with no
within-tree feature interactions. Its starting probabilities are class frequencies:

| Forecast stage/source | Cut | Hold | Hike |
|---|---:|---:|---:|
| Initial class-frequency prediction | 11.76% | 68.63% | 19.61% |
| After all tree updates | 12.37% | 69.72% | 17.91% |
| Kalshi at the same cutoff | 96.00% | 2.50% | 1.50% |
| Polymarket at the same cutoff | 97.49% | 2.36% | 0.15% |

Previous scheduled policy contributes −0.425 to the cut logit, while weak
three-month payroll growth contributes +0.186. Other macro inputs partly offset
the policy-history effect, but the net update barely changes the cut probability.
These are fitted-model score contributions, not causal economic effects. Correct
weak labor data reached the classifier; its computations left it near its
historical starting point. That establishes underreaction in this episode, not
that stronger updates would universally generalize.

## Development/test retraining mismatch

The original search fits once at the start of four development blocks containing
7, 7, 6 and 6 meetings. Actual test forecasting refits before every meeting.
Both avoid future information, but they evaluate different procedures and can
rank settings differently.

The diagnostic repeats exactly the existing 48 tree configurations on the same
26 development meetings, refitting before each. Test observations and labels
are excluded before any fitting or scoring in this search.

| Same per-meeting development protocol | Parameters | Brier | Cut-weighted Brier |
|---|---|---:|---:|
| Original selection | depth 1, learning rate .03, 40 rounds, leaf 10, L2 1 | .295731 | .374611 |
| Selection with matching refit schedule | depth 2, learning rate .10, 40 rounds, leaf 10, L2 1 | .257702 | .336564 |

The original model's replay exactly matches its archived walk-forward development
predictions. Its original block-search Brier was .324045; that different-protocol
score is not used as the table's comparator.

All three development cuts are in 2019 and in the first block. Both configurations
still identify zero of three cuts by argmax, with one false cut call each. Better
development probability scores do not demonstrate that missed cuts are fixed.
The new diagnostic winner has not been scored on test data or installed as the
baseline.

Cut emphasis is implemented through cut-component-weighted Brier for selection
and a separate missed-cut-cost decision rule. Actual tree fits minimize ordinary
multiclass log loss; individual cut rows are not reweighted. Stronger weighting
would need calibration checks and cannot itself supply missing information or
repair incorrect class rankings.

## Missing information and existing controls

The market comparison froze the 12-feature macro baseline, which excludes yields,
futures, market probabilities and Fed communications. It is a useful macro-only
control; these results do not establish it as a strong near-meeting model.

In his [August 22 speech](https://www.federalreserve.gov/newsevents/speech/powell20250822a.htm),
Powell discussed rising employment downside risks and the possibility that the
outlook justified adjusting policy. This preceded issuance but has no representation
in our feature vector. It is a plausible contributor to market expectations;
this audit cannot isolate its causal effect on prices.

Newer saved yield models give the September cut 19.5% with trees and 29.9% with
the small ordered yield/policy model, versus 12.4% for the original trees. They
remain far from the markets' 96–97.5%.

On the common six meetings, Brier is .377166 for original trees, .292159 for
yield-augmented trees, .317508 for the ordered yield model, .006417 for Kalshi
and .003907 for Polymarket. These are previously computed controls, not newly
fitted alternatives. Their full 26-meeting ranking differs; see the
[yields report](yields_results.md). Treasury yields also reflect a longer period
than this one scheduled decision.

## How much is the small sample driving the gap?

September 2025 explains 57.7% of the total Kalshi/tree Brier difference on the
common six. Removing that meeting for diagnosis leaves tree Brier .195405 versus
Kalshi .007210 on the other five. The miss dominates part of the gap, not all of
it. On Kalshi's ten-meeting sample, September explains 31.6% of the gap. These
calculations do not replace the headline samples.

Brier is an average, so small sample size does not mechanically lower it. But the
common six contain no hikes, nearby meetings share policy cycles, and missing
history may select particular eras or liquidity conditions. The future size of
the advantage remains uncertain.

## Next steps

1. Align development selection with per-meeting refitting in a separately versioned
   experiment, preserving the original baseline. Later historical test results
   remain exploratory.
2. Expand direct market history; compare all models on identical meetings and
   cutoffs. Keep macro-only models as controls for information value.
3. Evaluate the end of policy pauses explicitly. Learning that cuts follow cuts
   is insufficient for predicting a new cut; yields help but do not solve this.
4. Use prospective forecasts for confirmation. This audit provides no evidence
   that synthetic rows or a larger architecture alone would close the gap.

## Reproduce

```sh
export UV_CACHE_DIR=.cache/uv MPLCONFIGDIR=.cache/matplotlib LOKY_MAX_CPU_COUNT=1
uv run --frozen python scripts/diagnose_market_gap.py
uv run --frozen python scripts/verify_market_baseline.py reports/market_baseline_runs/176b1d70bbfe
uv run --frozen pytest -q
```

The diagnostic uses cached empirical artifacts and makes no network calls. It
saves exact tree-score contributions, transitions, feature lineage, per-meeting
error gaps, matched controls, quote bounds and development candidate predictions.
Its fingerprint includes inputs, relevant source code and the dependency lock;
original artifact hashes are checked unchanged after execution.

All 26 exact refits and tree-score reconstructions pass. All inputs to the 12
used features at all 26 cutoffs pass availability checks. The market verifier
passes, all 73 tests pass, and the diagnostic passes lint. No existing empirical
forecast or model choice was changed.
