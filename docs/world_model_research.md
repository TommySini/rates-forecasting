# World models, synthetic data and sample efficiency

Research notes, 2026-10-30. Question: can world models make the 159 labeled
meetings (17 cuts) go further, either by generating useful synthetic data or by
improving sample efficiency some other way? Nothing here is implemented. Repo
measurements below come from the cached panel, inventory and ALFRED vintages.

## Short answer

World models buy sample efficiency when **dynamics can be learned from abundant
data and the scarce signal is low-dimensional**. In Dreamer and MBPO the scarce
resource is environment interaction: every transition trains the dynamics model,
which is then reused many times. The analogue here is real: economic releases
are abundant (decades of monthly vintages); the Fed reaction function is scarce
(159 labels). The design goal is to learn as much as possible from the abundant
part and leave a handful of parameters for the labels.

Synthetic data only adds information through what the generator knows that the
labels do not: **other data it was fit on, or structural assumptions**. Synthetic
decisions sampled from a model fit to the same 159 meetings are self-distillation:
at best regularization, never new evidence about the Fed. Every synthetic design
below therefore names its external information source and receives a weight λ
selected chronologically, with λ = 0 (the current baseline) always in the grid.

Before any synthetic data: 48 real, already-labeled meetings are currently unused.

## Repo facts that shape the options

Measured on 2026-10-30 from local data:

1. **Treasury yields are effectively unrevised.** In the cached ALFRED vintages
   (from 2005-06-28), 0.05% of DGS10 and 0.02% of DGS2/DGS3MO daily observations
   ever take two values. For comparison: CPI 96%, payroll and industrial
   production 99%, unemployment 56%. The 2006 primary start is set by ALFRED's
   yield-archive start, not by yield revisions.
2. **Macro vintages go much further back.** ALFRED first vintages: PAYEMS
   1955-05-06, UNRATE 1960-03-15, CPIAUCSL 1972-07-21, CPILFESL 1996-12-12,
   INDPRO 1927-01-26. The local cache only requested vintages from 2004.
3. **The inventory already labels 2000–2005.** 48 sourced scheduled meetings:
   10 cuts, 16 hikes, 22 holds. Adding them takes N 159 → 207, cuts 17 → 27,
   hikes 24 → 40. Eight of the ten cuts are the 2001 cycle, so the effective
   gain in independent cut episodes is far smaller than ten.
4. **Release-path integration affects about a third of meetings.** Under the
   conservative availability rule, 56/159 meetings have a new CPI (34) or
   payroll (22) reference period arriving between issuance and decision,
   including 8 of 17 cuts. Step 3 of the research-plan world model can only
   change forecasts through those meetings.
5. **Development 2013–2018 contains zero cuts**, so no current selection
   procedure can validate cut detection.

## Options, ranked by expected value per unit effort

### 1. Recover real labels first

Not a world model, but the largest available lever. Extend the primary panel to
January 2000:

- Yields before June 2005 come from the current vintage under an explicit
  "effectively unrevised" assumption, justified by fact 1, recorded as its own
  `availability_method`, with a predeclared sensitivity that drops those rows.
- Macro inputs use genuine ALFRED vintages (fact 2); this needs new downloads
  with an earlier real-time start.
- The 2001 easing cycle in early data lets chronological validation contain a
  cut cycle, e.g. leave-one-cycle-out over 2000–2018, fixing fact 5.
- Block resampling should respect cycles; 2001 is one episode.

1994–1999 labels remain partly unresolved in the inventory. Before February 1994
the FOMC did not announce decisions, so pre-1994 target changes (e.g. the
Hamilton–Jordà series from 1984) define a different label and belong in a
separate auxiliary task, not the same target.

### 2. Economic structure as pseudo-data

[Del Negro and Schorfheide (2004)](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1468-2354.2004.00139.x)
is the established template for "a world model creates synthetic data": a VAR
prior equivalent to λT artificial observations simulated from a DSGE model. λ → 0
recovers the data-only VAR; λ → ∞ recovers the DSGE; λ is estimated. Two levels:

**2a. Structured policy head (cheap).** Replace the 3-class multinomial head with
an ordered model on a latent desired-rate gap: an inertial Taylor-type index of
inflation, unemployment gap and current rate, with cut/hold/hike thresholds and
priors centered on published rule coefficients. It uses class ordering and
change magnitude (25/50/75 bp, already in `rate_change_bps`) and has about six
parameters instead of dozens. [Hamilton and Jordà (2002)](https://www.journals.uchicago.edu/doi/abs/10.1086/341872)
model the funds-rate target this way (conditional hazard plus ordered probit).
Informative priors are pseudo-observations in closed form.

**2b. Simulated economies (medium).** Simulate a small New Keynesian model, or
[FRB/US stochastic simulations](https://www.federalreserve.gov/econres/us-models-python.htm)
(public `pyfrbus`, shocks drawn from historical residuals), with a policy rule
discretized to 25 bp moves. Randomize structural and rule parameters over a
prior ([domain randomization](https://arxiv.org/abs/1703.06907)). Train on real
plus synthetic meetings, giving synthetic rows total weight λ · N_real, and select
λ on chronological folds. External information: model structure and historical
shock distributions. FRB/US is quarterly and needs a meeting-frequency mapping;
start with the NK model. Required control: a deliberately misspecified rule
(e.g. weak inflation response) must not help. If it does, any gain is generic
shrinkage rather than economics.

### 3. Latent state-space world model trained on abundant releases

This sharpens the design already in `research_plan.md`. Fit dynamics on every
eligible release, not only labeled meetings: long vintage histories (fact 2) and
[FRED-MD](https://www.stlouisfed.org/research/economists/mccracken/fred-databases)
(about 128 monthly series from 1959; vintage archives from 1999-08). Dynamic factor
nowcasting ([Giannone, Reichlin and Small 2008](https://www.sciencedirect.com/science/article/abs/pii/S0304393208000652))
handles the "ragged edge" of staggered releases, which is exactly the
irregular-release problem. Start linear-Gaussian; Dreamer-style neural latents
([Hafner et al. 2025](https://www.nature.com/articles/s41586-025-08744-2)) depend on
millions of transitions and do not fit this scale.

Uses, in order of expected value:

- **Compressed state as input.** Two or three filtered factors replace 17 raw
  features, so the label-fitted head needs fewer parameters.
- **Auxiliary self-supervised targets.** Predict upcoming CPI/payroll values and
  the issuance-to-decision change in the two-year yield, a dense,
  meeting-specific signal about policy expectations.
- **Privileged training-only target.** Philadelphia Fed
  [Tealbook/Greenbook projections](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/greenbook)
  (1966–2020) are the staff forecasts the FOMC actually saw; Orphanides (2001,
  AER) shows policy rules fit much better on such real-time staff data. They are
  never model inputs: they were public only after a five-year lag. As an
  auxiliary target the state learns to infer the staff outlook from public data.
  Within expanding-window training, each projection becomes a usable target only
  after its own public release.
- **Release-path integration** (research-plan step 3). The
  [MBPO](https://arxiv.org/abs/1906.08253) lesson is to use short rollouts branched
  from real states, because model error compounds. Here the horizon is at most
  seven days and one or two releases, so compounding is small, but only the 56
  meetings in fact 4 can benefit. Report them separately.

### 4. Prior-fitted networks

[TabPFN](https://www.nature.com/articles/s41586-024-08328-6) is a transformer
pretrained on more than 100 million synthetic datasets that performs approximate
Bayesian prediction in context, strongest on small tables. It is a cheap fourth
baseline inside the existing expanding-window protocol. Caveats: its prior is
generic (neither economic nor temporal), rows are treated as exchangeable,
weights/licensing must be checked, and another model means another look at an
already-examined holdout.

The research version is a "macro-PFN": pretrain on the randomized simulated
economies from 2b, giving amortized inference over reaction functions. Related:
[amortized simulation-based inference for DSGE state-space models](https://arxiv.org/html/2210.07154),
[a transformer trained mostly on DSGE-simulated trajectories](https://arxiv.org/html/2512.21031v1),
and [Simulacrum](https://arxiv.org/html/2606.27711) (2026 preprint). Sim-to-real
transfer is the untested assumption. High effort; only after 2b shows signal.

### 5. Pool other central banks

The [BIS policy-rate dataset](https://data.bis.org/topics/CBPOL) covers dozens
of economies, mostly from 1980. A hierarchical reaction function (shared state
structure, bank-specific coefficients, partial pooling) could multiply decision
counts roughly tenfold, scored only on the Fed. Hard parts: foreign real-time
vintages, decision calendars and instrument changes. Medium-high effort.

## Not recommended

- **GAN, diffusion or TimeGAN rows fit to this panel.** The generator learns from
  the same 159 meetings, adds no information, learns rare cut tails worst and
  can memorize.
- **SMOTE or oversampling cuts.** It inflates minority probabilities and harms
  calibration without improving discrimination ([van den Goorbergh et al. 2022](https://academic.oup.com/jamia/article/29/9/1525/6605096));
  a threshold shift gives the same recall. The repo's cost-weighted decision rule
  already does this without altering probabilities. A
  [2025 Fed-forecasting preprint](https://arxiv.org/html/2506.22763v1) used SMOTE and
  saw AUC rise but accuracy fall.
- **LLM-simulated FOMC meetings or LLM-written synthetic histories.** LLMs recall
  historical macro values and outcomes ([Lopez-Lira et al.](https://arxiv.org/pdf/2504.14765),
  [Federal Reserve Board 2025](https://www.federalreserve.gov/econres/feds/files/2025044pap.pdf)),
  breaking point-in-time integrity. Only post-cutoff forward evaluation is clean.
- **Off-the-shelf time-series foundation models in historical backtests.**
  Several were pretrained on FRED-MD itself ([Carriero, Pettenuzzo and Shekhar](https://arxiv.org/html/2407.00890v5)),
  and date-aligned retraining materially changes forecasts
  ([look-ahead study](https://arxiv.org/html/2609.20554)). Acceptable only in the
  forward log.

## Evaluation rules for any synthetic-data experiment

- Synthetic weight λ is a hyperparameter chosen on chronological development
  folds; λ = 0 is always a candidate.
- Generators are fit inside each training fold, only on information available
  at that cutoff. Synthetic rows are never scored.
- Controls separate "economics helped" from "shrinkage helped": misspecified
  priors, random structure, and plain L2 at matched effective regularization.
- Report per class (especially cuts) and the 56 release-in-window meetings
  separately, alongside the unchanged baselines.
- The historical holdout has been examined; all results remain exploratory,
  and the forward forecast log is the confirmation.

## Suggested sequence

1. Extend the panel to 2000 with the yield-assumption sensitivity; redesign
   validation to contain a cut cycle; rerun existing baselines as a new
   exploratory fingerprint.
2. Ordered Taylor-type head with literature priors (2a) and a TabPFN baseline (4).
3. Simulated-economy pseudo-data with a λ grid (2b), New Keynesian model first.
4. Linear-Gaussian state-space world model with auxiliary targets (3).
5. Cross-bank pooling (5) or macro-PFN only if steps 2–4 show structure helps.
