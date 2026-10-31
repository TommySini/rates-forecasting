# Initial baseline experiment — 2026-10-30

The empirical pipeline runs end to end, including a fully cached offline replay.
No synthetic observations enter these results. Predictions, metrics, plots, raw
responses, detailed lineage and tests are saved locally.

## Coverage

Official meeting inventory: 302 entries spanning 1994–2025, including intermeeting
and non-policy sessions. All **207 scheduled decisions in 2000–2025** have sourced
numerical labels; the earlier inventory remains partly unresolved.

Primary macro panel: **2006-01-31 through 2025-12-10, 159 meetings**:

| Split | Meetings | Hold | Hike | Cut |
|---|---:|---:|---:|---:|
| Training 2006–2012 | 56 | 44 | 4 | 8 |
| Development 2013–2018 | 48 | 39 | 9 | 0 |
| Historical holdout 2019–2025 | 55 | 35 | 11 | 9 |

Nine audited economic series yield 33,081 vintage observation records, 19 candidate
features and **17 primary model features**. Claims are audit-only because their
vintages start in 2009. Treasury vintages begin June 2005, determining the primary
start. Unknown release times use vintage date + one federal business day at
18:00 New York time, including yields. Two original BLS release timestamps were
also verified and stored without relaxing availability. See [source audit](../docs/source_inventory.md).

The [first snapshot](snapshot_2019-07-31.md), July 24, 2019 at 22:00 UTC, reconstructs
payroll growth of 224,000 and unemployment of 3.7%, matching the original BLS
release. All 19 features agree exactly with reconstruction from the full panel.

## Historical holdout results

Development-selected settings: logistic C=1; trees L2=10, depth=2, 80 iterations,
learning rate=.05, minimum leaf=15. Each forecast refits on expanding history;
labels enter training only after permitted availability. No class rebalancing or
holdout tuning.

| Model | N | Brier ↓ | Log loss ↓ | Accuracy |
|---|---:|---:|---:|---:|
| Smoothed historical frequency | 55 | 0.554243 | 0.954629 | 63.64% |
| Regularized logistic regression | 55 | 0.403111 | 0.705628 | 72.73% |
| Shallow boosted trees | 55 | 0.370494 | 0.675817 | 80.00% |

Always-hold accuracy is **63.64%**, supplied as context only.

Brier is `(1/N) Σ_i Σ_k (p_ik − 1[y_i=k])²`, summing over cut/hold/hike.
Range [0,2]; **no division by three**. Log loss is the mean negative natural log
of the realized-class probability, clipped below at 1e-15 for numerical stability.

| Paired Brier difference | Mean | 95% block-bootstrap interval |
|---|---:|---:|
| Logistic minus frequency | −0.151132 | [−0.459886, 0.124491] |
| Trees minus frequency | −0.183749 | [−0.466890, 0.025025] |
| Trees minus logistic | −0.032617 | [−0.187985, 0.129860] |

Intervals use 1,000 paired circular moving-block draws, eight meetings per block.
They describe uncertainty under local dependence; few cycles and regime change
limit interpretation. **All intervals include zero.**

Both learned models improve average historical scores. This benchmarks direct
supervised prediction; it says nothing yet about world models or PSI and does
not establish a robust advantage in future regimes.

Trees get 10/11 hikes and 32/35 holds correct, but only **2/9 cuts**. Logistic gets
8/11 hikes, 27/35 holds and 5/9 cuts. Mean Brier on actual cuts is 1.090539 for
trees versus 0.639027 for logistic. Development contains no cuts, limiting model
selection for this failure mode. Large errors include logistic's 1.9% hike
probability before March 2022 and low cut probabilities before July 2019 and
September 2024. These events remain in the scores.

Calibration plots include five fixed bins, counts and block-bootstrap intervals.
Some bins contain only one or two meetings. Degenerate intervals in tiny bins
are not certainty; these results do not establish reliable calibration.

## Prespecified sensitivity

| Availability rule | Frequency Brier | Logistic Brier | Trees Brier |
|---|---:|---:|---:|
| Vintage + 1 business day | 0.554243 | 0.403111 | 0.370494 |
| Vintage + 2 business days | 0.554243 | 0.381499 | 0.363687 |

The extra day changes feature values/ages for 155/159 meetings. Model settings
stay fixed. Ranking is unchanged; the better-looking lag is not selected after
seeing these scores.

Excluding 2020: Brier 0.624420 / 0.423911 / 0.421530 for frequency/logistic/trees.
For the seven executed 2020 meetings: 0.073030 / 0.260479 / 0.020532.
The tree advantage over logistic is much smaller outside 2020.

**Zero scored meetings have an intervening emergency change**, so that subgroup
has N=0 and no estimable score. Cancelled March 18, 2020 remains in the
[exclusions ledger](exclusions.csv), with the March 11 issuance convention and
March 15 intervention recorded. It is not labeled a hold. Earlier emergency
changes correctly update the next scheduled meeting's before-target state.

## Audit and limitations

[Quality audit](data_quality_audit.json) and [independent verification](verification.json)
pass. **37 focused tests** and Ruff pass. The verifier independently recomputes
scores, checks observed training labels and 337 raw-response hashes, and compares
the initial snapshot with the scaled reconstruction. Both plot types were
visually inspected. Full offline reproduction succeeded.

Five primary feature cells are missing: four stale yield/slope values before
January 2006 and stale industrial production before December 2025. They stay
explicit and are imputed inside training only. Eighty early announcement times
are unknown; actual timestamps remain null and label eligibility is delayed.
Historical schedules are retrospective, not separately archived at issuance.
ALFRED metadata do not certify perfect historical completeness. Early 1994–1999
label repair remains outside the primary sample.

The [market audit](../docs/prediction_market_audit.md) recovered historical samples
for five Kalshi September 2025 and four Polymarket September 2024 contracts.
Outcome gaps, ambiguous wording, cancellation rules, and upper-bound versus
midpoint definitions prevent a certified three-class comparison. Candle/sample
timestamps do not establish executable prices or actual quote-update times.
No trading simulation ran.

## Artifacts and reproduction

Current primary run: [primary-7ec22ca842a3](runs/primary-7ec22ca842a3/complete.json).
Sensitivity: [lag2-e01743e7e7c2](runs/lag2-e01743e7e7c2/complete.json).

- [Predictions](runs/primary-7ec22ca842a3/predictions.parquet)
- [Probability plot](runs/primary-7ec22ca842a3/probabilities.png)
- [Model-comparison table](runs/primary-7ec22ca842a3/model_comparison.csv)
- [Calibration plot](runs/primary-7ec22ca842a3/calibration.png) and [counts](runs/primary-7ec22ca842a3/calibration.csv)
- [Largest errors](runs/primary-7ec22ca842a3/largest_errors.csv)
- [Class results](runs/primary-7ec22ca842a3/by_class.csv), [period results](runs/primary-7ec22ca842a3/by_period.csv), [paired uncertainty](runs/primary-7ec22ca842a3/paired_differences.csv)

The first historical evaluation remains in `primary-108c458519e0`. A later
provenance-only replay added verified BLS publication times without changing
availability, features, modeling choices or predictions. Both primary and
sensitivity prediction tables are exactly unchanged. Replays are retained in
[evaluation_history.jsonl](evaluation_history.jsonl); future modeling iterations
are exploratory and require forward confirmation.

Reproduce: `uv sync --frozen`, `uv run --frozen rates all --offline`,
`uv run --frozen pytest -q`, and `uv run --frozen python scripts/verify_outputs.py`.
The [README](../README.md) includes environment/cache settings and fresh-download
commands. All needed raw responses are cached in this workspace.

**Next: additional baseline and data review**, especially rare-cut calibration,
archival schedule/timestamp gaps, and a forward evaluation protocol. Review
those findings before implementing the small state-space extension in the
[research plan](../docs/research_plan.md). No world-model or PSI training has run.
