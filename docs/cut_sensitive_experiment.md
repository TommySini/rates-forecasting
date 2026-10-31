# Chronological 75% / 12.5% / 12.5% experiment

Requested on 2026-10-30 after reviewing the original benchmark. This is an
**exploratory experiment**: its development and test meetings were already part
of the original historical holdout. Resplitting does not make them untouched.
The original configuration, reports, and immutable runs are retained.

## Split and chronology

`configs/cut_sensitive.yaml` allocates ordered meetings by largest-remainder
rounding, without dropping observations. For 159 meetings:

| Split | N | Decision dates | Cuts | Holds | Hikes |
|---|---:|---|---:|---:|---:|
| Initial training | 119 | 2006-01-31–2020-12-16 | 11 | 95 | 13 |
| Development | 20 | 2021-01-27–2023-06-14 | 0 | 10 | 10 |
| Historical test | 20 | 2023-07-26–2025-12-10 | 6 | 13 | 1 |

These fractions define initial boundaries. Training expands as earlier labels
become available. The development period is partitioned into four successive
five-meeting validation blocks. Each candidate fits once before each block using
only then-available labels, and predicts the block's individually dated feature
snapshots. Later blocks may train on earlier development labels after publication.
No shuffling, stratification across time, or random early-stopping split is used.

Aggregate each candidate's validation score equally over meetings, not equally
over potentially unequal blocks. Freeze settings before test scoring. Final test
forecasts refit at each meeting using only previously available labels. Separately
saved selected-model development predictions also use per-meeting retraining;
they are not the block-CV scores used to select settings. Every CV candidate,
fold, training cutoff, split assignment and selected setting is saved.

**There are no development cuts.** Cut recall is therefore undefined there. This
search cannot validate better detection of actual cuts; its cut-probability term
only penalizes false cut probabilities in this period. The specified split is
retained, and no test cuts are moved into validation. Additional cycle-spanning
chronological validation would be a separate, explicitly specified experiment.

## Search space and optimization

The full Cartesian grid contains 55 candidates and 220 development fits:

- Frequency alpha: 0.5, 1, 2 (3 candidates).
- Logistic C: 0.01, 0.1, 1, 10 (4 candidates).
- Trees: depth 1/2/3, learning rate .03/.1, boosting iterations 40/100,
  minimum leaf size 10/20, L2 1/10 (48 candidates).

The budget is capped at 60 candidates; an oversized grid fails explicitly.
All statistical parameters exposed by the existing model families are searched.
The logistic family remains L2-regularized multinomial regression. Median
imputation, missing indicators and training-only scaling remain fixed. Numerical
solver settings, random seed, feature definitions, loss family and histogram
implementation defaults are fixed design choices, not additional tuning targets.
Trees remain shallow and disable random early stopping.

Logistic regression uses gradient-based L-BFGS optimization of regularized log
loss. Histogram gradient boosting builds successive trees using derivatives of
log loss. Frequency smoothing is calculated directly; it has no gradient descent.
Hyperparameter CV is an outer loop over settings, distinct from fitting a model's
coefficients or trees. See the official [logistic documentation](https://scikit-learn.org/1.8/modules/generated/sklearn.linear_model.LogisticRegression.html),
[boosting documentation](https://scikit-learn.org/1.8/modules/ensemble.html), and
[time-series CV guidance](https://scikit-learn.org/1.8/modules/cross_validation.html#cross-validation-of-time-series-data).

## More weight on cut errors

The configurable multiplier is fixed at **2**, a transparent moderate preference,
not an estimated optimal cost or an inverse-frequency weight. Two mechanisms
implement it without silently changing what the probability columns mean.

Candidate selection minimizes component-weighted Brier:

`2 * (p_cut - y_cut)^2 + (p_hold - y_hold)^2 + (p_hike - y_hike)^2`.

This penalizes both missed cut probability and false cut probability. The weights
apply to probability components on every meeting, not only to meetings whose
realized outcome was a cut. For true probabilities q, expected loss is
`sum_k w_k * ((p_k - q_k)^2 + q_k * (1 - q_k))`, minimized at p=q. Thus this
scoring rule still rewards truthful probabilities. Its unnormalized range is
[0,3] at weight 2. Standard unweighted Brier [0,2], log loss, calibration and
ordinary accuracy continue to be reported. The original primary metric remains
standard Brier; the additional score is this experiment's selection objective.

Training itself still uses unweighted log loss. Class reweighting training rows
would change the target distribution and could inflate reported cut probabilities;
it is not silently introduced as a probability-calibration fix.

A separate decision rule assigns cost 2 to failing to call an actual cut, cost 1
to every other incorrect call, and cost 0 to a correct call. Minimize expected
cost by selecting the largest of `2*p_cut`, `p_hold`, `p_hike`. Those three values
are **decision scores, not probabilities**. The stored probability vector is
unchanged. Ordinary accuracy continues to use the largest original probability.
`cut_diagnostics.csv` separately reports both decision rules' cut recall,
precision, missed cuts, false cut calls and overall accuracy. Undefined recall
or precision stays missing rather than becoming a misleading zero.

More cut calls can trade fewer misses for more false alarms. No improvement is
guaranteed. In particular, an argmax change is not evidence of better probabilities.

## Reproduction

With the existing cached empirical panel:

```sh
UV_CACHE_DIR=.cache/uv MPLCONFIGDIR=.cache/matplotlib LOKY_MAX_CPU_COUNT=1 \
  uv run --frozen rates evaluate --config configs/cut_sensitive.yaml --offline
uv run --frozen pytest -q
uv run --frozen python scripts/verify_outputs.py
```

The split changes evaluation only; economic availability rules, feature values,
source data and policy labels are unchanged. Results live under a separate
`reports/runs/cut_sensitive_75-<fingerprint>/` directory and are logged in the
evaluation history. Future meetings remain necessary for fresh confirmation.
