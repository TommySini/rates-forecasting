# World models and synthetic data: research and first experiment

2026-10-30. The user requested research into world-model architectures that can
use scarce economic data more effectively, and comparison with existing models.
This specification was recorded before running the new pilot. Historical tests
remain exploratory; synthetic data cannot create independent test meetings.
The earlier [research memo](world_model_research.md) is preserved separately;
its original 159-meeting measurements predate the completed 207-meeting extension.

## What the literature supports

| Approach | Research evidence | Relevance and limitation here |
|---|---|---|
| Small dynamic factor/state-space model | [Bok et al., New York Fed Staff Report 830](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr830.pdf) describes latent-factor nowcasting that updates as macro data arrive. | A defensible starting architecture for partial, asynchronous economic information. Their task is macro nowcasting; it is not evidence of superior Fed-decision forecasts. |
| Short model-generated trajectories | [Janner et al., MBPO](https://arxiv.org/abs/1906.08253) studies the tradeoff between generated experience and model bias, and uses short rollouts starting from real states. | Borrow the discipline of short, anchored simulations. This is an analogy from reinforcement learning, not a guarantee for macro forecasting or a reason to add trading/RL. |
| Learned sequence generator | [Yoon et al., TimeGAN](https://papers.nips.cc/paper_files/paper/2019/hash/c9efe5f26cd17ba6216bbe2a7d26d490-Abstract.html) combines embedding, supervised and adversarial objectives for temporal sample generation. | A possible later baseline. A larger generator can reproduce or distort a small number of economic regimes; realistic-looking paths do not validate their Fed labels. |
| Synthetic-prior pretraining | [Dooley et al., ForecastPFN](https://proceedings.neurips.cc/paper_files/paper/2023/hash/0731f0e65559059eb9cd9d6f44ce2dd8-Abstract-Conference.html) trains on synthetic time series to approximate inference under a generating prior. | A promising later direction: sample many plausible economic dynamics rather than one fitted economy. It transfers assumptions; it does not manufacture evidence about the Fed's reaction function. |
| PSI-style structure integration | [Kotar et al., PSI](https://arxiv.org/abs/2509.09737) alternates probabilistic modeling, structure extraction and reintegration; its reported instance used 1.4 trillion video tokens. | Test only after a functioning economic predictor. Its visual results do not establish that synthetic macro scenarios solve policy-label scarcity or identify causal responses. |
| Economic-model priors via artificial observations | [Del Negro and Schorfheide, DSGE-VAR](https://fraser.stlouisfed.org/files/docs/historical/frbatl/wp/frbatl_wp_2002-14a.pdf) expresses restrictions from an economic model as a weighted prior on a statistical forecaster. | This is a direct macroeconomic precedent for synthetic-data regularization. Its VAR/quarterly setup is not a result about our scheduled-meeting classification target. |

My recommendation is a small probabilistic state-space model first, followed by
a hierarchical/Bayesian dynamics ensemble if the diagnostic results justify it.
The useful hypothesis is that learning economic dynamics from non-meeting data
helps policy prediction. The number of artificial rows is not itself evidence.

## What data we actually have

There are 207 labeled scheduled meetings and 27 cuts. The five-series macro
archive contains 14,214 observation/version records but only **335 monthly
reference periods and 1,675 series-months**. Series and adjacent months are
correlated; revisions are not independent economic outcomes. A macro prediction
objective supplies additional real supervision, with much less gain in
independent sample size than the raw archive count suggests.

An ex-post audit counts first available series-months strictly after issuance
and before the decision date starts, using the existing conservative availability
rule. Of 207 windows, 110 contain none of the five series' new periods, and 134
contain no new CPI/employment period. These counts describe archive availability,
not independently known historical release schedules or independent release
events. They never enter a model. This limits how much seven-day forecasts can
benefit specifically from simulating incoming releases.

## Recommended architecture

Use a compact latent economic state z, monthly dynamics
`z[t+1] = F z[t] + process_noise`, and an observation model
`macro[t] = center + scale * (H z[t] + measurement_noise)`.
Condition on only the economic observations available at each forecast cutoff.
Use the policy target/history and economic information to produce a three-class
probability distribution. Ultimately sample parameters as well as states so that
economic model uncertainty is not mistaken for certainty.

The first executable pilot uses two latent factors and five transformed monthly
channels: headline/core CPI month-over-month percentage changes, payroll change
in thousands, unemployment percent, and industrial-production monthly percent
change. Fit loading directions by PCA on complete, eligible training months;
fit a ridge VAR(1) to adjacent factors; estimate Gaussian process/measurement
noise; and filter partially observed months with a Kalman filter. This is an
approximate two-stage estimator, not the full New York Fed model, an EM fit, or
a fully Bayesian posterior. Factors do not have identified economic/causal names.

Freeze two factors, ridge 1, maximum transition spectral radius .98, and a .05
standardized measurement-variance floor. Use no neural-network pretraining or
additional dependency. World-model normalization and parameters fit only through
the last training meeting's feature timestamp. Current released observations may
update the filtered state at validation/test issuance, but do not refit parameters.
Every historical training snapshot itself resolves revisions as of its own cutoff.
The fitted representation is a training-fold transformation, like a fitted scaler;
its parameters are not claimed to have existed at each older training timestamp.

## Safe synthetic training in this pilot

For each real training meeting, draw 32 plausible latent states from its filtered
Gaussian state distribution. Retain that meeting's actual observed policy label
and unchanged observed features. Each draw receives weight **1/32**, so all views
of a meeting together have weight one. These are uncertainty-regularized views
of a real labeled example, not 32 independently observed Fed responses.

Optimize the average classification loss over these latent views. This is an
expected-log-loss augmentation objective, not exact joint marginal-likelihood
training. The state distribution is inferred from macro data, not conditioned
on a fabricated policy label. At prediction, average 256 conditional probability
vectors over latent-state draws. Use deterministic antithetic samples for lower
Monte Carlo noise. Keep imputation/scaling fitted only to real training feature
rows and latent means; duplicating views does not change their statistics.

This deliberately does **not** attach a historical decision label to an arbitrary
different CPI path. Nor does it label invented economic histories with our own
classifier and count those labels as fresh evidence. Such self-training can
reinforce the original model's mistakes.

## Comparisons fixed before test evaluation

Use the unchanged 155/26/26 split and the same four chronological development
blocks as the expanded benchmark. Tune C in {.01,.1,1,10} separately for each
new classifier using the existing cut-component Brier weight 2. Standard Brier,
log loss and calibration remain probability outcomes; missed-cut cost 2 remains
a separately reported decision rule.

1. Existing frozen frequency/logistic/trees on the same 26 real test meetings.
2. `history_logistic`: existing 12 features plus the previous 12 monthly rows of
   the five eligible transformed series, with training-only imputation/scaling.
3. `noise_control`: original features with independent Gaussian training jitter
   of .1 training standard deviations; 32 views with total weight one per meeting.
4. `wm_mean`: existing features plus two filtered state means; ordinary logistic.
5. `wm_integrated`: same training approach, but integrate probabilities over state
   uncertainty at prediction. This isolates uncertainty integration.
6. `wm_augmented`: train with posterior state draws and integrate at prediction.
   Compare especially against `wm_integrated` to isolate synthetic training.

The same macro fit is reused across candidates in each fold. Final parameters
are selected and logged before test prediction. Refit on expanding eligible
history at each test meeting. Report all variants, not only the best score.
All evaluations use real decisions; test uncertainty uses paired meeting blocks.
No synthetic rows increase test N, calibration bin counts or bootstrap sample size.

## Check the economic predictor separately

Before looking up future actuals, forecast each transformed series' next missing
reference month. Compare its Gaussian distribution with persistence using only
training-estimated innovation variance. Score the first permitted available
vintage, with prior-period revisions known at that availability cutoff. This
target is not necessarily a release that arrives before the Fed meeting.
Do not infer an ex-ante release calendar from its realized publication date.

Save per-series CRPS, Gaussian negative log density and 90% interval coverage.
Scores use natural channel units; standardized CRPS divides by the training-only
scale for an additional comparison. Missing/already-known targets remain flagged.
These are forecasts of subsequent macro observations, not extra labeled policy
examples. Overlapping targets and related series are not independent replications.

## What comes after this pilot

The model can also generate three-month economic paths, saved with synthetic
labels and without publication timestamps or invented policy outcomes. They are
illustrations of its assumptions, not empirical training/test records. Their
Gaussian tails can be economically implausible, and parameter uncertainty is
not yet integrated. A next version should use a small Bayesian/state-space
ensemble, heavy-tailed or bounded measurements, and an audited release calendar.

Only then test simulation of releases between issuance and the meeting, with a
policy head trained for that information state. Average conditional decisions
over unknown release paths. A specified future CPI scenario is conditional
analysis, not an identified causal intervention. Keep seven days primary; a
separately specified 14/28-day experiment may expose more of this mechanism.

Later synthetic-prior pretraining would sample plausible dynamics/measurement
parameters within training folds and train a small inference network across
those artificial economies. Any reaction-function prior must be disclosed and
tested against manually engineered structure. PSI extraction/reintegration stays
within training folds and requires matched information/compute controls.

Historical improvements remain exploratory. The actual scarcity of independent
easing cycles and future test decisions is unchanged, regardless of how many
paths are generated. No world-model advantage is assumed in advance.

## Structural synthetic data as a separate next experiment

The strongest distinct mechanism in the earlier memo is to add **explicit
external economic structure**, rather than just sample the same fitted model.
One candidate is a small New Keynesian/state-space simulator with randomized
inflation persistence, demand/supply shocks, policy inertia and reaction
coefficients. Its generated policy labels are consequences of the assumed rule,
not newly observed Fed behavior. A simpler ordered cut/hold/hike reaction head
with economic priors should be the first control.

Following the DSGE-VAR idea, cap the total influence of artificial examples at
lambda times the real-data weight and choose lambda in development, including
zero. Compare against ordinary shrinkage and deliberately incorrect or shuffled
structure. This tests whether the economic assumptions help, not whether a large
synthetic dataset can force their answers. Calibration, a meeting-frequency
mapping, and honest forward testing remain required. This structural simulator
is **not implemented** in the latent-augmentation pilot.
