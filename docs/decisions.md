# Decisions recorded before performance evaluation

2026-10-30:

- Python 3.12 with uv and `uv.lock`; local Parquet and immutable HTTP cache.
- Full meeting inventory targets 1994–2025. All 207 scheduled announcements in
  2000–2025 can be labeled; 1994–1999 holds/early statements require further work.
- Primary macro panel: **2006–2025**, 159 executed scheduled meetings. Treasury
  archives start June 2005. Start with the next full year; do not pretend older
  observation dates establish older vintage availability.
- Initial claims are retained in candidate/audit tables but **excluded from the
  primary model** because vintage history begins May 2009. Primary uses 17
  numerical features, with training-fitted missing indicators added by imputation.
- Fixed split: training 2006–2012 (56), development 2013–2018 (48), historical
  holdout 2019–2025 (55). Last complete year selected, no partial 2026 results.
- All eligible meetings remain even with stale/missing features. Missing values
  are imputed within each training fit, never with future panel statistics.
- July 24, 2019 snapshot reviewed and passed before full macro ingestion.
- Official June 2007 statement URL contains `20070618`, but its release header
  says June 28. Parse the header; test against regression to URL-date inference.
- September 15, 2003 is a communications discussion, not another scheduled
  policy decision. March 18, 2020 is cancelled, not an invented hold.
- Multiclass Brier = mean sum of three squared probability errors, range [0,2].
  Log loss uses natural log with true-class probability clipped below at 1e-15.
- Laplace frequency smoothing alpha=1. Logistic C in {0.1,1}; trees depth 2,
  80 boosting iterations, learning rate .05, minimum leaf 15, L2 in {1,10}, no
  random early-stopping split. No class rebalancing or post-hoc calibration.
- Select by development Brier. No performance threshold. Always-hold accuracy
  is context only, never submitted as deterministic competing probabilities.
- Uncertainty: paired circular moving-block bootstrap of meeting scores,
  block length 8 meetings, 1,000 draws. Calibration bins fixed at width .2 and
  use the same block resampling. Small dependent samples remain uncertain.
- Sensitivities declared in advance: two-day vintage lag with unchanged model
  settings; emergency-period subsets; same feature and target definitions.
- Record every holdout evaluation in `reports/evaluation_history.jsonl`. Reuse
  an identical completed fingerprint; changed runs are explicitly exploratory.
- Market history is a separate audit, not a prerequisite for macro forecasting.
  No probability normalization across incompatible/incomplete contract sets.
- No orders, brokerage connection, purchases, or external publication.

## Subsequent exploratory experiment: 75% / 12.5% / 12.5%

2026-10-30, after the original holdout was examined, the user requested a larger
training share, more emphasis on missed cuts, and broader hyperparameter CV.
The user clarified the split as 75% training / 12.5% development / 12.5% test.
The [experiment specification](cut_sensitive_experiment.md) records the 119/20/20
rounding, four chronological validation blocks, all 55 candidate settings,
fixed cut-component weight 2 and missed-cut decision cost 2 before running this
experiment. Development still has zero cuts; the test has six. Keep this explicit.
Original model settings and reports remain the initial benchmark. New results are
exploratory, even though the revised code never tunes on its designated test set.

## Extended early history

Later on 2026-10-30 the user requested the 48 labeled 2000–2005 meetings. The
[prespecified extended-history design](extended_2000.md) uses all 207 meetings
with 12 policy/macro features that have audited vintages over the longer span.
Retain 75/12.5/12.5 rounding (155/26/26), the prior 55-candidate search and cut
costs. The 2001 cycle remains in training; development now includes 2019 cuts.
Compare a 2006-start control with identical features and test dates, and a
fixed-settings sensitivity removing the eight 2001 training labels. Keep all
2001 decisions in the main experiment and avoid treating them as independent
episodes. The January 2001 snapshot was checked against original Fed/BLS releases
before scaling. Preserve original files through a separate dataset directory.

## Structured reaction model

2026-10-31, after the world-model pilot showed no Fed-forecast gain, the user
requested step 1 of the world-model research: a small ordered Taylor-type
reaction model with published priors. The [specification](structured_policy_model.md)
fixed the seven-parameter model, lower-bound rule, λ grid, wrong-prior and
free-coefficient controls, and interpretation rules before test scoring. Reuse the
extended 155/26/26 split and development folds. Declared scipy explicitly (it was
already locked through scikit-learn). Results and a clearly labeled post-hoc
ablation are in [policy_model_results.md](../reports/policy_model_results.md).

## Market probabilities as the external benchmark

2026-10-31, the user requested retirement of standalone logistic regression and
market-implied probabilities as another baseline. New comparisons use shallow
boosted trees plus available market forecasts; previous models and reports remain
reproducible. The [market protocol](market_benchmark_plan.md) fixes quote selection,
mapping assumptions and coverage-matched scoring. The public-data implementation
uses Kalshi target-rate thresholds and six reviewed Polymarket partitions, with
explicit price reconciliation only inside those related exhaustive outcomes.
CME requires a separate access decision and publication-time audit. All results
remain exploratory, and tiny cohorts receive no misleading bootstrap intervals.

## Treasury yields for 2000–2025

2026-10-31, the user asked to restore yields after the structured-policy results.
The [specification](extended_2000_yields.md) treats daily DGS3MO/DGS2/DGS10 values
dated before ALFRED's first vintage (2005-06-28) as unrevised, available on their
observation date plus one business day, labeled in every lineage row; code refuses
the assumption for other series. A separate `extended_2000_yields` dataset keeps
the original artifacts. Registered comparisons: retuned trees with yields, an
untuned momentum-only ordered model, a momentum-plus-market-spread ordered model,
and a 2006-start training sensitivity, scored on all 26 test meetings and the 14
after-hold meetings. Following the user's direction, logistic regression is not
part of the new comparison. Results: [yields_results.md](../reports/yields_results.md).

## 1-month Treasury yield

2026-10-31, the user chose the free 1-month bill as the first longer-history
market signal. The [specification](extended_2000_bills.md) adds DGS1MO as an
optional feature (present only when configured, so earlier panels are unchanged)
in a separate `extended_2000_bills` dataset, reviews an October 2001 snapshot
against the original H.15 release, and fixes one comparison: the market model
with and without the 1-month spread. Result: not helpful
([bills_results.md](../reports/bills_results.md)). Market-overlap outputs are now
named by model run, so comparisons no longer overwrite each other.
