# Treasury yields restored: computed results

Specification: [docs/extended_2000_yields.md](../docs/extended_2000_yields.md),
recorded before the pre-2005 yield download. Runs: 17-feature baselines
[`extended_2000_yields-9a335a20f13e`](runs/extended_2000_yields-9a335a20f13e/complete.json)
and ordered models [`24f35e51a919`](policy_model_runs/24f35e51a919/complete.json).
All verifiers pass. Results are exploratory: these test years were used before.

## Headline

Adding two market spreads to the three-parameter momentum model is the largest
improvement so far, and most of it is at turning points. Both registered
conditions for "yields help the small model" are met. Yields do **not** help the
boosted trees.

## Results on the same 26 real test meetings

"After a hold" means the previous scheduled decision was a hold, so a move would
end a pause: 14 meetings (11 holds, the July 2023 hike, the September 2024 and
September 2025 cuts). Brier: lower is better, range 0–2.

| Model | Parameters | Brier, all 26 | Brier, 14 after a hold | Cuts caught (false calls) |
|---|---:|---:|---:|---|
| `market_ordered`: last move + 3-month and 2-year spreads | 5 | **0.252** | **0.198** | 3 of 6 (0) |
| `market_ordered_post2005` (sensitivity) | 5 | 0.293 | 0.208 | 3 of 6 (0) |
| `momentum_ordered`: last move only | 3 | 0.343 | 0.362 | 4 of 6 (1) |
| `taylor_ordered_12f` (frozen) | 7 | 0.343 | 0.352 | 4 of 6 (1) |
| `trees_12f` (frozen) | — | 0.425 | 0.386 | 3 of 6 (1) |
| `trees_17f` (with yields, retuned) | — | 0.432 | 0.422 | 3 of 6 (1) |

Spreads are the yield minus the announced policy midpoint; negative means
markets price lower rates. Paired Brier differences, 8-meeting block bootstrap,
descriptive 95% intervals:

| Comparison | All 26 | After a hold |
|---|---|---|
| momentum − market | +0.092 [+0.001, +0.189] | +0.164 [+0.103, +0.225] |
| market (post-2005 training) − market | +0.042 [−0.025, +0.117] | +0.010 [+0.005, +0.015] |
| trees with yields − trees without | +0.007 [−0.078, +0.084] | +0.036 [−0.033, +0.097] |

## The three turning points

| Meeting | Outcome | Market spreads (3m, 2y) | market_ordered | momentum | trees_17f |
|---|---|---|---:|---:|---:|
| 2023-07-26 | hike after a pause | +0.37, −0.38 | 26% hike | 11% | 45% |
| 2024-09-18 | first cut | −0.26, −1.69 | **47% cut** | 10% | 13% |
| 2025-09-17 | cut after a pause | −0.28, −0.88 | **30% cut** | 10% | 19% |

It also cut the false alarm after the December 2024 cut: January 2025 cut
probability 29%, against 59% for momentum. It still does not *call* a turning
point (47% cut versus 53% hold in September 2024), but the probabilities move a
long way in the right direction. At the last refit the weights are 2.5 per
25 bp of previous move, 6.5 per point of 3-month spread and 1.4 per point of
2-year spread. The 3-month bill carries most of the signal.

## Registered interpretation

- **"Yields help the small model": met.** Lower Brier than momentum on all 26
  meetings and on the 14 after-hold meetings. Three moves in that subset keep
  the evidence weak; development scores agree (0.122 versus 0.208).
- **"Yields help trees": not met** (0.432 versus 0.425).
- **Pre-archive assumption:** training only from 2006 keeps about 94% of the
  after-hold gain and about 55% of the overall gain. Turning-point improvement
  does not rest on the 2000–2005 yield assumption; part of the overall gain does.

## What this means

The 3-month bill yield is largely **the market's own forecast** of the next few
months of policy. This model mostly learns how to read that forecast, not how
the economy works. That is legitimate information at issuance, and it is now the
bar: an economic world model only adds value if it beats `market_ordered`,
especially after pauses. The trees again failed to use a strong signal that a
small structured model used easily.

## Limitations

Twenty-six test meetings, three turning points, repeated use of these test years;
five 2005 meetings without archived yields; 2000–2005 yields assumed unrevised
(checked exactly against the original H.15 release for the snapshot week).
The replay `584a1196036a` has identical forecasts; its `test_parameters.csv`
recorded the unfiltered training count for the post-2005 sensitivity, fixed in
`24f35e51a919`.

## Reproduce

```sh
export UV_CACHE_DIR="$PWD/.cache/uv" MPLCONFIGDIR="$PWD/.cache/matplotlib" LOKY_MAX_CPU_COUNT=1
uv run --frozen rates snapshot --config configs/extended_2000_yields.yaml   # needs FRED_API_KEY once
uv run --frozen rates panel --config configs/extended_2000_yields.yaml
uv run --frozen rates evaluate --config configs/extended_2000_yields.yaml --offline
uv run --frozen python scripts/run_policy_model.py configs/policy_yields.yaml
uv run --frozen python scripts/verify_policy_model.py reports/policy_model_runs/24f35e51a919
```

Source changes alter run fingerprints; a replay writes a new directory, and the
reference paths in `configs/policy_yields.yaml` must then point to it.

## Against market-implied probabilities

[`scripts/compare_market_overlap.py`](../scripts/compare_market_overlap.py) scores
the frozen forecasts above on exactly the meetings where Codex's
[market baseline](market_baseline_results.md) (run `176b1d70bbfe`) recovered
eligible quotes. Nothing was refit. Results:
[comparison table](market_overlap_24f35e51a919_comparison.csv) and
[per-meeting probabilities](market_overlap_24f35e51a919_meetings.csv).

| Meetings | Kalshi | Polymarket | market_ordered | momentum | trees_17f |
|---|---:|---:|---:|---:|---:|
| Kalshi coverage, 10 | **0.035** | — | 0.320 | 0.373 | 0.393 |
| Shared coverage, 6 (2025) | 0.006 | **0.004** | 0.318 | 0.386 | 0.292 |

Markets are roughly ten times better by Brier on these meetings. At a seven-day
horizon the Fed has usually signaled its decision, and markets price that
guidance (speeches, minutes, press conferences); our inputs do not see it. For
September 2025, Kalshi gave the cut 96% and `market_ordered` 30%. The samples are
small and selected by quote availability, so the size of the gap is uncertain;
its direction is not.

**Timing check.** The script asserts that every market forecast uses the model's
exact issuance time (18:00 New York, seven days before the decision) and that
every quote used is at or before it: 0–1 hour earlier, never later
([timing table](market_overlap_24f35e51a919_timing.csv)). Issuance falls 4.7–5.8 days after
the Fed's communications blackout began (midnight on the second Saturday before
the meeting, per the [FOMC policy](https://www.federalreserve.gov/monetarypolicy/files/FOMC_ExtCommunicationStaff.pdf)),
so the Fed's pre-meeting guidance was already public to both forecasters, and this
meeting's statement and press conference came after both. The comparison is
same-time; the gap is information the market uses (Fed speeches before the
blackout, minutes, the previous press conference and projections, news), not a
later forecast time.
