# Market benchmark protocol

2026-10-31. The user requested market-implied probabilities as the external
benchmark and shallow boosted trees as the statistical baseline. Logistic
regression is retired from this new comparison; historical code, settings and
results remain available for reproduction. No tree retraining or tuning is
needed to compare the saved forecasts on matching meetings.

## Implementation plan

1. Inspect official CME, Kalshi and Polymarket documentation and cached research.
2. Review contract targets and recover one cutoff snapshot before expanding.
3. Freeze the rules below, retrieve available public quotes for the existing
   26 test meetings, and publish every inclusion/exclusion.
4. Compare market probabilities and the frozen trees on identical meetings;
   save probabilities, proper scores, accuracy, cut diagnostics and calibration.
5. Document paid-access limitations, timing differences and the next data work.

The source audit recovered Kalshi September 2025 target-rate quotes and reviewed
Polymarket's six May–December 2025 event definitions before this protocol was
implemented. No aggregate market score was used to select these rules.

## Kalshi target-rate thresholds

Use public historical markets in series `KXFED`, including legacy `FED-*`
identifiers. Select contracts explicitly resolving on the upper target bound
being **greater than** a threshold following the specified scheduled meeting.
Let U be the upper target known at issuance, a=price(U_after > U-.25), and
b=price(U_after > U). Then use `(p_cut,p_hold,p_hike)=(1-a,a-b,b)`.

This conversion assumes a 25-bp target grid, unchanged range width, and no
intervening emergency change. Rate-level contracts are not generally the same
target as the scheduled meeting's rate change. Flag emergency/width-changing
cases as incompatible under this fixed rule, with explicit exclusion records.
Do not infer U from the future meeting's after-rate or before-rate. Use the last
announced policy target available at issuance. Do not assign zero probability to
an unlisted strike or missing quote.

Use hourly bid/ask closing midpoints at or before issuance. Request seven days
of history; reject missing/crossed quotes, spread above .10, sample age above
24 hours, or a<b. Do not repair crossed threshold probabilities or normalize
these overlapping binary contracts. Save a last-trade-price sensitivity only
where both actual candle trade closes exist. Candle age is not quote-update age;
zero-sided books and quote-update uncertainty remain flags, not claims of liquidity.

## Polymarket related outcome partitions

Primary eligibility is limited to the six manually reviewed May–December 2025
events in `configs/market_baseline.yaml`. Each has the same rules across four
outcomes: 50+ bp cut, 25 bp cut, hold, 25+ bp hike. Their rounding clause maps
nonstandard changes to the next 25-bp bucket, preserving direction. All contracts
refer to the upper target bound immediately before/after the scheduled meeting.
The fallback treats no statement by the next meeting as hold; that differs from
our cancellation exclusion. Upper-bound versus midpoint compatibility requires
unchanged range width. Current rule text is retrospective metadata, not a verified
archive of wording as it stood at forecast time.

Retrieve the Yes token's hourly CLOB price history; choose the last sample at or
before issuance, age at most 24 hours. Preserve all four observed prices and their
sum. Only for this reviewed related partition, reject sum deviations above .05
and divide all prices by their sum to obtain a coherent probability proxy. This
explicit proportional reconciliation is not a normalization of unrelated bets.
Also report a Euclidean simplex projection sensitivity on the same meetings.
Historical bid/ask and execution costs are unavailable from this endpoint.

Older discovered events remain in the inventory but outside this primary mapping:
some have contradictory hike wording, an unmapped "Other" outcome, ambiguous
integer-bp bins or an incorrect scheduled date. Do not resolve them using outcomes.

## Evaluation and evidence limits

Use the existing seven-day, 18:00 New York convention (UTC storage), unchanged
26-meeting historical test cohort, and exact saved tree probabilities. Compute
each provider's own coverage-matched comparison plus the shared intersection.
No market parameters are learned. Standard multiclass Brier (sum over classes,
range 0–2) remains primary; natural-log loss clips at 1e-15; accuracy uses argmax.
Keep the existing missed-cut-cost-2 decision rule separate from probability scores.
Report class counts and dependence-aware paired intervals, cautiously for tiny
samples. A repeated historical comparison is exploratory. Prices can reflect
risk premia, spreads and liquidity, so calibration is an empirical question.

Correctness refinement after the first run: when a cohort contains fewer than
two prespecified eight-meeting blocks, suppress bootstrap/calibration intervals
and report point differences and counts only. A block spanning the whole sample
produces a degenerate mean interval. This changes uncertainty reporting, not
probabilities, inclusion rules or any model setting. The exact reviewed
Polymarket rule texts are now pinned by SHA-256 for fresh-download validation.

CME access remains a separate decision: official documentation advertises daily
history for meetings from January 2015, with end-of-day subscription access and
OAuth entitlement. Its 01:45 UTC publication is later than our 18:00 New York
cutoff; use only a previously available release unless a documented historical
calculation/publication timestamp proves otherwise. Intraday API history starts
November 1, 2025. Do not buy access or silently use future end-of-day snapshots.
