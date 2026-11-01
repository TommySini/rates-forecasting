# Research plan

Question: can learning shared economic dynamics and reusable structure improve
scheduled Fed decision probabilities over small direct supervised models when
labeled policy events are scarce? The first milestone is an auditable dataset
and a useful benchmark even if every more complex model loses.

The initial system makes a seven-calendar-day cut/hold/hike forecast from the
information available at 18:00 New York time. It keeps event labels, publication
times, vintage values, and input lineage separate. The fixed baseline protocol,
metrics and split are in `decisions.md`; source limitations are explicit in
`source_inventory.md`. Evaluate historical-frequency, regularized logistic and
shallow boosted-tree models chronologically. Save predictions before interpreting
aggregate performance. Historical holdout reuse is exploratory and logged.

## Next gate: review data and baselines

Inspect original-announcement spot checks, missing/stale observations, sample
representativeness, calibration counts, paired score uncertainty and availability
sensitivity. The small sample spans few policy cycles. A better aggregate score
does not establish reliable probabilities in every regime. Before expanding
architecture, repair material source/label issues and establish a forward forecast
log; genuine future decisions provide confirmation beyond reused history.

## Completed first pilot

The [world-model pilot](world_model_pilot.md) now implements a two-factor Gaussian
state-space approximation, fitted to eligible monthly macro histories, and a
regularized policy classifier. It compares latent means, probability integration,
weighted latent-state augmentation, generic noise and a direct history control
against the frozen expanded baselines. The same 26 real test meetings remain the
evaluation sample. [Results](../reports/world_model_results.md) show no Fed-score
advantage from this augmentation; macro-release diagnostics improve on persistence
in four of five channels. All results are exploratory, without subsequent tuning.

This is a limited test of state estimation and uncertainty regularization. It
does not implement the full release-path design below, parameter uncertainty,
structural pseudo-labels or PSI extraction. The earlier
[research memo](world_model_research.md) is preserved as context; its original
sample counts predate the extension to 207 meetings.

## Full economic release-path model (design only)

Start with a compact probabilistic state-space model, e.g. latent inflation
pressure, labor-market slack and activity momentum. Estimate transition and
measurement uncertainty with strong regularization, using only dated economic
releases and contemporaneously available revisions. Model irregular release
times explicitly; a monthly value carried for twenty days is one release, not
twenty independent observations.

At each issuance:

1. Filter a distribution over latent economic state using the eligible release history.
2. Forecast distributions for upcoming inflation and employment releases, respecting
   their known release schedule and the remaining days before the meeting.
3. Draw plausible release paths, update state along each path, and apply a compact
   conditional policy model.
4. Average conditional cut/hold/hike probabilities over the paths, retaining
   parameter and observation uncertainty where practical.

Fit probabilistic economic-release likelihoods jointly or in a staged procedure
with policy-decision classification. Tune regularization on chronological
development folds. Compare with the unchanged direct baselines under identical
information and scoring. Ablate state dynamics, release prediction and parameter
sharing to locate any improvement. Use a small recurrent model only if the data
and state-space results justify the added flexibility.

A specified future CPI number defines a **conditional scenario**. An unconditional
forecast integrates over unknown releases. Neither exercise alone identifies a
causal intervention; policy, releases and expectations are jointly determined.

## PSI-inspired experiment (after a working world-model baseline)

[World Modeling with Probabilistic Structure Integration](https://arxiv.org/abs/2509.09737)
cycles probabilistic prediction, extraction of compact structure, and reintegration
as conditioning signals or prediction targets. Its visual-task results followed
large-scale video pretraining (the abstract reports 1.4 trillion tokens); they do
not establish a solution to macroeconomic sample scarcity.

Only after reviewing the economic world-model benchmark:

1. Within each training fold, query standardized economic scenarios to extract
   compact response patterns (e.g. nonlinear sensitivity conditional on inflation
   and labor state). Do not inspect validation/holdout responses for extraction.
2. Integrate those patterns as conditioning features or auxiliary targets, then
   retrain with a fixed budget.
3. Compare with the unchanged predictor, matched information and comparable
   compute, plus manually engineered economic features and random/control
   structures to test whether extraction adds something distinct.
4. Evaluate calibration, per-class errors, chronology and release-prediction
   distributions, not just one favorable policy metric.

Synthetic scenarios are queries of a trained model, not new independent
historical evidence. Any zero-shot claim requires a precisely specified held-out
task definition and evaluation; ordinary future-meeting prediction is not that
claim. Negative results should retain the dataset, reproducible benchmark and
clear explanation of which hypothesis failed.

Large transformers, multi-agent economic simulators, general news scraping,
LLM-generated historical narratives, trading execution and dashboards are outside
this initial milestone.
