# Structured Fed reaction model: computed results

Run [`14f31bd8c716`](policy_model_runs/14f31bd8c716/complete.json), specified in
[docs/structured_policy_model.md](../docs/structured_policy_model.md) before any
test score was computed. Test years were examined in earlier experiments, so
everything here is **exploratory**. Independent verification passed.

## Headline

The small ordered models score far better than every earlier model on the same
26 real test meetings (November 2022–December 2025). **But the improvement does
not come from the Taylor rule.** A deliberately wrong economic prior does just as
well, and a post-hoc three-parameter model that only knows the Fed's previous
move matches the full model. The working ingredient is: "the Fed tends to keep
moving in the same direction," estimated without heavy shrinkage, on an ordered
cut < hold < hike scale with cuts ruled out at the zero lower bound.

## Registered results

Brier: mean over meetings of the summed squared probability errors (0–2, lower
is better). Always-hold accuracy is 14/26 = 53.85%.

| Model | Selected | Brier | Log loss | Accuracy | Cuts caught (of 6) |
|---|---|---:|---:|---:|---:|
| Taylor ordered, published prior | λ = 1 | **0.3431** | **0.5615** | **76.9%** | 4 |
| Taylor ordered, wrong prior (control) | λ = 0.01 | **0.3388** | 0.5715 | 76.9% | 4 |
| Ordered, free coefficients (control) | C = 0.01 | 0.4924 | 0.8129 | 65.4% | 0 |
| Multinomial logistic, same 5 inputs | C = 0.01 | 0.5246 | 0.8813 | 65.4% | 0 |
| Existing shallow trees, 12 features | frozen | 0.4248 | 0.7358 | 73.1% | 3 |
| Existing logistic, 12 features | frozen | 0.5077 | 0.8641 | 65.4% | 0 |
| World-model pilot, augmented | frozen | 0.5096 | 0.8667 | 65.4% | 0 |
| Historical frequency | frozen | 0.6369 | 1.0669 | 53.8% | 0 |

Cuts are counted by largest probability. The missed-cut cost rule gives the same
counts for both Taylor models, 1 for the free ordered and small logistic
controls and the existing logistic, and 4 for the existing trees. Paired Brier differences, 8-meeting circular
block bootstrap, descriptive 95% intervals:

| Comparison | Mean | Interval |
|---|---:|---|
| Taylor ordered − existing trees | −0.082 | [−0.158, −0.003] |
| Taylor ordered − existing logistic | −0.165 | [−0.256, −0.051] |
| Taylor ordered − free ordered control | −0.149 | [−0.271, −0.034] |
| Wrong prior − Taylor ordered | −0.004 | [−0.031, +0.021] |

Per class, the Taylor model gets 4/6 cuts, 11/14 holds and 5/6 hikes right.

## Pre-registered interpretation

- **"Economic structure helps": not established as specified.** The Taylor model
  beats the free ordered control and the small logistic on test, but its
  development score (0.3932 cut-weighted Brier) is worse than the wrong-prior
  control's (0.3836). The rule required both.
- **"Published priors help": not supported.** The selected λ = 1 beats λ = 0 in
  development (0.3932 vs 0.4207), but the wrong prior beats λ = 0 by more. Any
  shrinkage of the two policy weights helps; the published values do not.

## Where the improvement comes from (post-hoc, after seeing test scores)

[`scripts/posthoc_policy_ablation.py`](../scripts/posthoc_policy_ablation.py)
refits three untuned variants on the same 26 meetings. None was used to select
anything; treat them as diagnosis, not results.

| Variant | Parameters | Brier |
|---|---:|---:|
| Ordered, previous scheduled move only | 3 | 0.3432 |
| Taylor ordered, λ = 0 | 7 | 0.3519 |
| Ordered, free coefficients, weak ridge C = 10 | 7 | 0.3568 |

1. **Momentum alone matches the full model.** Knowing only the previous scheduled
   move scores 0.3432, against 0.3431 for the selected Taylor model.
2. **The registered free control lost through over-shrinkage, not a missing
   Taylor form.** With a weak ridge it scores 0.3568; development selected the
   strongest ridge (C = 0.01), which flattens the momentum coefficient together
   with everything else. The 12-feature logistic and tree models have the same
   problem.
3. **The data do not support Taylor weights.** Fitted on all pre-test meetings
   without the prior, the inflation weight is a_π = −0.77 (total response 0.23,
   below one-for-one) and a_u = 3.2. Core CPI barely moves the forecast.
4. **Every cut it caught followed a cut.** November and December 2024, October and
   December 2025 receive 0.55–0.93 cut probability. Both turning points, the
   first cuts of September 2024 and September 2025, receive about 0.10. The one
   false cut call is January 2025, right after the December 2024 cut.

Fitted at each test refit, the selected model keeps a_π ≈ 0.50, a_u ≈ 1.00 (held
by the prior), gap sensitivity s ≈ 0.19 per point and momentum ≈ 2.4 per 25 bp.
See [test_parameters.csv](policy_model_runs/14f31bd8c716/test_parameters.csv).

## What this means

- The bottleneck in earlier models was over-regularization of the one strong
  signal, not a lack of economic structure. A tiny ordered model fixes that.
- The **momentum-only ordered model is the honest baseline to beat** from here.
  Its forecasts amount to "repeat the last move with roughly 55–90% probability."
- The unsolved problem is **turning points**: the first cut or hike after a pause.
  That is where economic dynamics, world models and market expectations would
  have to earn their place. Of 67 scheduled moves since 2000, 21 followed a hold
  and only 10 ended a pause of 200 days or more, so any claim there will be weak
  without future meetings.

## Limitations

Twenty-six test meetings within one hiking-then-easing cycle; repeated use of the
historical test years; post-hoc diagnosis after seeing scores; constant neutral
rate and unemployment benchmark; core CPI as a stand-in for PCE inflation;
yields and market expectations excluded from this 12-feature dataset.

## Reproduce

```sh
export UV_CACHE_DIR="$PWD/.cache/uv" MPLCONFIGDIR="$PWD/.cache/matplotlib" LOKY_MAX_CPU_COUNT=1
uv run --frozen python scripts/run_policy_model.py
uv run --frozen python scripts/verify_policy_model.py reports/policy_model_runs/14f31bd8c716
uv run --frozen python scripts/posthoc_policy_ablation.py
uv run --frozen pytest -q
```

Completed identical runs are reused. Adding scipy as a declared dependency
changed only the project entry in `uv.lock`; source or lock changes alter run
fingerprints, so older experiments rerun into new directories if replayed.
