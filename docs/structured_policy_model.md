# Structured Fed reaction model: specification

Recorded 2026-10-31, before computing any test score for these models. Test
years were examined in earlier experiments, so all results are exploratory.

## Why this experiment

Every tuned model so far chose the strongest simplification on offer: logistic
C=0.01, depth-1 trees with the fewest iterations, and C=0.01 for all five
world-model pilot heads. The labels (207 meetings, 27 cuts) cannot support many
learned numbers. The world-model pilot improved the description of the economy
but not the Fed forecast, so the bottleneck is the reaction part.

This experiment replaces the roughly 39 learned numbers of the 12-feature
logistic model with a 7-parameter reaction rule whose form comes from economics,
and optionally starts its two policy weights at published values.

## Model

Inputs, all already in the extended panel and point-in-time audited: core CPI
year-over-year inflation π, unemployment u, announced policy midpoint i,
previous scheduled change m (basis points), and the three-month unemployment
change Δu. None are missing in the 2000–2025 panel; training-median imputation
is kept for robustness.

1. **Rule rate** (Taylor-type): `R = 2 + π + a_π (π − 2) − a_u (u − 5)`.
2. **Gap**: `g = R − i`, percentage points. Positive means the rule says rates
   are too low.
3. **Pressure**: `z = s · g + b_m · (m / 25) + b_Δu · Δu`. `s > 0` is how sharply
   decisions respond to the gap; `b_m` captures the Fed's tendency to keep moving
   in the same direction; `b_Δu` captures reaction to a deteriorating job market
   beyond the unemployment level.
4. **Ordered outcome** (logistic noise): `P(cut) = σ(τ_cut − z)`,
   `P(cut or hold) = σ(τ_hike − z)`, `τ_cut < τ_hike`.
5. **Lower bound**: when the announced midpoint is at most 0.125 (a 0–0.25%
   range), a cut is impossible; its probability mass is assigned to hold. This
   affects 72 of 207 meetings (January 2009–March 2022: 70 holds, 2 hikes) and no
   test meeting. Without it, the rule gap would call for cuts at every one of them.

Seven parameters: `τ_cut`, `τ_hike − τ_cut` (log scale), `s` (log scale), `a_π`,
`a_u`, `b_m`, `b_Δu`. The 2% neutral real rate and 5% unemployment benchmark are
fixed constants; constant errors in either are absorbed by the thresholds.
Real-time drift in the neutral rate over 2000–2025 is **not** modeled; this is a
stated limitation.

## Priors

Published values: Taylor (1993) uses 0.5 on the inflation gap and 0.5 on the
output gap. With an Okun factor of about 2 between output and unemployment gaps,
that is `a_π = 0.5`, `a_u = 1.0`. Prior: independent normals with these means
and standard deviation 0.5, with precision multiplied by `λ · N_train`. As in
Del Negro and Schorfheide (2004), prior influence therefore scales with the
real sample, and λ is its weight relative to the real data. The equivalence to
"λ · N imaginary meetings" is approximate for this nonlinear model.

Fixed weak priors keep every fit defined at λ = 0 and apply to all variants:
`a_π`, `a_u` sd 5 around the same centers; `log s ~ N(0, 2²)`;
`b_m, b_Δu ~ N(0, 2²)`; `τ_cut ~ N(0, 10²)`; `log(τ_hike − τ_cut) ~ N(log 2, 2²)`.

Grid: λ ∈ {0, 0.01, 0.03, 0.1, 0.3, 1}.

## Comparisons

All new variants use the unchanged 155/26/26 split, the same four
chronological development blocks, selection by cut-component-weighted Brier
(weight 2), ties broken by standard Brier and then the smaller grid value.

1. `taylor_ordered`: the model above, λ grid.
2. `taylor_wrong_prior`: identical, but both prior centers moved to deliberately
   wrong values, `a_π = −0.5` (inflation response below one-for-one) and
   `a_u = −1.0` (tightening as unemployment rises). Same λ grid, tuned separately.
   If it matches `taylor_ordered`, the published values are not what helps.
3. `ordered_free`: ordered logit on the same five inputs with free linear
   coefficients on training-standardized inputs and the same lower-bound rule.
   Ridge penalty `‖β‖² / (2C)`, C ∈ {0.01, 0.1, 1, 10}. Isolates the Taylor form
   and priors from "ordered outcome plus few inputs".
4. `small_logistic`: the existing multinomial logistic pipeline on the same five
   inputs, C ∈ {0.01, 0.1, 1, 10}. Isolates the ordered structure.
5. Frozen references, copied unchanged: frequency, 12-feature logistic and trees
   from `extended_2000-b4a00efeac35`, and `wm_augmented` from world-model run
   `7185f66f7271`.

Selections are written to `reports/policy_model_evaluation_history.jsonl` before
any test prediction. Test forecasts refit at each meeting on labels available
before issuance. Fitted parameters are saved at every test refit.

## Interpretation rules, fixed in advance

- "Economic structure helps" requires `taylor_ordered` to have lower test Brier
  than both `ordered_free` and `small_logistic`, and lower development CV score
  than `taylor_wrong_prior`. With 26 test meetings, paired intervals are
  descriptive; confirmation needs future decisions.
- "Published priors help" additionally requires a selected λ > 0 whose
  development score beats λ = 0.
- Report every variant, per-class scores, cut diagnostics, calibration counts
  and fitted parameters, including unfavorable results. No specification change
  after seeing test scores; any follow-up is a new, separately recorded experiment.

## Commands

```sh
export UV_CACHE_DIR="$PWD/.cache/uv" MPLCONFIGDIR="$PWD/.cache/matplotlib" LOKY_MAX_CPU_COUNT=1
uv run --frozen python scripts/run_policy_model.py
uv run --frozen python scripts/verify_policy_model.py reports/policy_model_runs/<run>
uv run --frozen pytest -q
```
