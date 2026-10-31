# 75% / 12.5% / 12.5% exploratory experiment — 2026-10-30

The requested split and broader chronological cross-validation ran successfully.
Cut-sensitive decisions catch more cuts in this test, but the new selected models
do **not** improve probability scores over the original settings on the same
meetings. The original benchmark and its artifacts remain intact.

## Design and coverage

The same empirical 159-meeting panel and 17 inputs are used; no new observations,
synthetic empirical rows, availability assumptions, or labels were introduced.

| Split | Meetings | Dates | Cut | Hold | Hike |
|---|---:|---|---:|---:|---:|
| Initial training | 119 | January 2006–December 2020 | 11 | 95 | 13 |
| Development | 20 | January 2021–June 2023 | 0 | 10 | 10 |
| Historical test | 20 | July 2023–December 2025 | 6 | 13 | 1 |

Largest-remainder rounding gives 119/20/20. Training expands chronologically
after the initial boundary. Four successive five-meeting development blocks
evaluate all 55 candidates (220 fits). Their training counts are 119/124/129/134.
Each fold fits preprocessing and models using only labels available before its
first validation forecast. Test data never enter this search. Test forecasts then
retrain per meeting with frozen hyperparameters and available previous labels.

**No development meeting is a cut.** Cut recall cannot be validated there, and
the cut term in validation penalizes only false cut probabilities. This split
therefore remains a weak way to select models for detecting cuts. No test cuts
were moved into development. The whole experiment is exploratory because the
historical test meetings were previously examined in the original benchmark.

Candidate selection uses Brier with the cut probability component weighted 2,
and the hold/hike components weighted 1. This is a fixed preference, not an
estimated optimal weight. It preserves the truthful-probability optimum; training
still uses unweighted log loss. The [specification](../docs/cut_sensitive_experiment.md)
documents the formula, search ranges, optimization methods and decision costs.

Selected settings:

- Frequency: alpha 2.
- Logistic: C .1, L2 multinomial regression, L-BFGS.
- Trees: depth 3, learning rate .1, 100 iterations, minimum leaf 20, L2 10.

The ordinary and cut-weighted CV objectives selected **the same candidate for
each model** in this run. Thus the extra cut component weight did not change the
chosen probability models relative to ordinary scoring of this same candidate
search. The expanded search and new development period differ from the original
benchmark; this experiment does not isolate their separate effects.

## Probability results on the 20 test meetings

| Model | Standard Brier ↓ | Log loss ↓ | Argmax accuracy | Cut-weighted Brier ↓ |
|---|---:|---:|---:|---:|
| Frequency | .547323 | .985696 | 65% | .797773 |
| Logistic | .495793 | .833188 | 70% | .645189 |
| Trees | .522099 | .929016 | 60% | .695632 |

Always-hold accuracy is 65%. Standard Brier remains the sum over three classes,
range [0,2], with no division by three. Log loss is natural log with a 1e-15
numerical floor. The new weighted score has range [0,3]. Calibration counts and
paired block uncertainty are saved; every paired 95% Brier interval includes zero.
Twenty dependent test meetings and only one hike cannot establish robust ranking
or calibration across policy regimes.

For a fair comparison, restrict the previously saved original-model predictions
to these **same 20 meetings**, retaining their original hyperparameters. Both
experiments use the same available training histories at these forecast times:

| Original frozen settings | Standard Brier ↓ | Log loss ↓ | Argmax accuracy |
|---|---:|---:|---:|
| Frequency | .549840 | .994158 | 65% |
| Logistic | .446092 | .736709 | 70% |
| Trees | .481539 | .834052 | 70% |

The newly selected logistic and tree models have worse probability scores than
their original counterparts on these meetings. More hyperparameter search did not
guarantee improvement. This result is retained without another tuning pass.

## Missing cuts versus false cut calls

The separate cost-sensitive decision assigns cost 2 to a missed actual cut,
cost 1 to any other mistake, and zero to correct calls. It chooses the maximum
of `2*p_cut`, `p_hold`, `p_hike`; these are decision scores, not probabilities.
Stored probabilities, Brier, log loss and ordinary argmax accuracy are unchanged.

| Model / decision rule | Cuts caught / 6 | Missed cuts | False cut calls | Cut precision | Rule accuracy |
|---|---:|---:|---:|---:|---:|
| Frequency / argmax | 0 | 6 | 0 | undefined | 65% |
| Frequency / cut cost 2 | 0 | 6 | 0 | undefined | 65% |
| Logistic / argmax | 2 | 4 | 0 | 100% | 70% |
| Logistic / cut cost 2 | 4 | 2 | 1 | 80% | 75% |
| Trees / argmax | 2 | 4 | 2 | 50% | 60% |
| Trees / cut cost 2 | 3 | 3 | 2 | 60% | 65% |

The logistic decision rule raises cut recall from 33.3% to 66.7% with one false
cut alarm. That is a different use of the same probabilities, not an improvement
in the probability estimates. Six cuts are too few to assume this tradeoff will
repeat in future cycles. The original 2-of-9 tree statistic used a different,
55-meeting test; it is not directly comparable to 2-of-6 in this revised split.

## Artifacts, checks and reproduction

Run: [cut_sensitive_75-9ad944bb4528](runs/cut_sensitive_75-9ad944bb4528/complete.json).

- [CV candidates](runs/cut_sensitive_75-9ad944bb4528/cv_candidates.csv), [fold scores](runs/cut_sensitive_75-9ad944bb4528/cv_fold_scores.csv), [fold boundaries](runs/cut_sensitive_75-9ad944bb4528/cv_folds.csv).
- [Split assignments](runs/cut_sensitive_75-9ad944bb4528/split_meetings.csv), [selected settings](runs/cut_sensitive_75-9ad944bb4528/selected_models.json), [resolved configuration](runs/cut_sensitive_75-9ad944bb4528/resolved_config.json).
- [Test predictions](runs/cut_sensitive_75-9ad944bb4528/predictions.parquet), [comparison](runs/cut_sensitive_75-9ad944bb4528/model_comparison.csv), [cut diagnostics](runs/cut_sensitive_75-9ad944bb4528/cut_diagnostics.csv).
- [Probability plot](runs/cut_sensitive_75-9ad944bb4528/probabilities.png), [calibration plot](runs/cut_sensitive_75-9ad944bb4528/calibration.png), [largest errors](runs/cut_sensitive_75-9ad944bb4528/largest_errors.csv).

All **48 synthetic-fixture tests**, Ruff, and the independent artifact verifier
pass. New tests cover rounding/duplicates, CV publication cutoffs, invariance to
corrupted future test features/labels, bounded full-grid enumeration, weighting,
decision-cost tradeoffs and undefined recall. The verifier recomputes scores,
checks fold eligibility and selection, confirms test exclusion from all candidate
predictions, and checks every original run as well. Both new plots were inspected.

```sh
UV_CACHE_DIR=.cache/uv MPLCONFIGDIR=.cache/matplotlib LOKY_MAX_CPU_COUNT=1 \
  uv run --frozen rates evaluate --config configs/cut_sensitive.yaml --offline
uv run --frozen pytest -q
uv run --frozen python scripts/verify_outputs.py
```

Next useful research work is cycle-spanning chronological validation and forward
forecast logging. Changing this test after seeing its scores does not create
fresh confirmation; any additional historical modeling remains exploratory.
