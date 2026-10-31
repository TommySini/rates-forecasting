# Expanded 2000–2025 benchmark — 2026-10-30

All 48 labeled scheduled decisions from 2000–2005 are now used. They add 10 cuts,
16 hikes and 22 holds, producing **207 meetings: 27 cuts, 40 hikes, 140 holds**.
The historical probability scores improve against a matched 2006-start control,
but uncertainty and concentration in a few policy cycles remain substantial.

This is an exploratory result. The test years overlap previously examined
historical evaluations; new split boundaries do not create an untouched test.

## Data and audit

The original 17-feature benchmark remains intact. The expanded experiment uses
12 policy/macro features across the entire 2000–2025 sample. CPIAUCSL, CPILFESL,
PAYEMS, UNRATE and INDPRO supply 14,214 real-time observation/version records,
with observation warmup from 1998. Treasury yields and financial age are excluded
throughout because their audited vintages begin in June 2005; initial claims
remain excluded because of their later vintage start.

All 48 early meetings have complete values for the 12 included features. The only
missing model feature in the full panel is the already flagged stale industrial
production value before December 2025. The overlapping 159 meetings reproduce
all 12 features exactly from the original panel. Raw replies, retrieval metadata,
vintage intervals and input-level lineage are saved. Availability still uses the
conservative next federal business day at 18:00 New York, stored in UTC.

The [January 2001 snapshot](extended_2000/snapshot_2001-01-31.md) was checked before
the full panel build: payroll +105,000 and unemployment 4.0% match the original
BLS release; three-month payroll growth averages 76,666.67, matching its rounded
77,000. The policy feature correctly uses the 6.0% target after January 3's
emergency cut. January 31's scheduled cut is 6.0% to 5.5%, a separate -50 bp.
The [source review](../docs/extended_2000.md) links the original Fed/BLS releases.

The expanded panel has 128 unknown announcement publication times, including
all 48 early meetings; actual times stay missing and training eligibility uses
the documented conservative lag. No scored meeting has an intervening emergency
change. Cancelled March 18, 2020 remains an exclusion with its intervention flag.
Retrospective schedules and possible archive incompleteness remain limitations.

## Chronological split and tuning

The requested 75% / 12.5% / 12.5% split rounds to **155 / 26 / 26**:

| Split | Dates | Cuts | Holds | Hikes |
|---|---|---:|---:|---:|
| Initial training | February 2000–May 2019 | 18 | 108 | 29 |
| Development | June 2019–September 2022 | 3 | 18 | 5 |
| Test | November 2022–December 2025 | 6 | 14 | 6 |

The **2001 cycle is in training**. Development now includes the **2019 cut
cycle**, because adding earlier rows moves the percentage boundaries earlier.
All three development cuts occur in the first of four validation blocks;
development still contains only one easing cycle.

The same 55-candidate grid, cut-component weight 2, and missed-cut decision cost
2 were retained. Each of four chronological validation blocks fits on earlier
available labels only. Expanded-history training counts are 155/162/169/175;
validation counts are 7/7/6/6. Candidate scores weight meetings equally. Test
forecasts retrain per meeting after settings are frozen.

Selected expanded settings: frequency alpha 2; logistic C .01; trees depth 1,
learning rate .03, 40 iterations, minimum leaf 10, L2 1. The matched 2006-start
control uses the same 12 features, validation/test meetings and tuning budget,
but only 107 initial training rows. It selects the same frequency/logistic
settings and trees depth 2, rate .1, 100 iterations, minimum leaf 20, L2 10.
Thus the comparison tests the expanded-history modeling procedure, including
its development-selected settings, rather than isolating only sample size.

## Test results on the same 26 meetings

| Model | Brier, expanded ↓ | Brier, 2006 control ↓ | Log loss, expanded ↓ | Ordinary accuracy, expanded |
|---|---:|---:|---:|---:|
| Frequency | .636944 | .672542 | 1.066945 | 53.85% |
| Logistic | .507742 | .522279 | .864115 | 65.38% |
| Trees | .424813 | .474947 | .735772 | 73.08% |

Always-hold accuracy is 53.85%. Standard Brier is the sum of three squared errors,
range [0,2], not divided by three. Log loss uses natural log and a 1e-15 numerical
floor. Cut-weighted selection scores, calibration counts, class/year results and
all per-meeting probabilities are saved separately.

Expanded minus control Brier differences are -.035598 (frequency), -.014537
(logistic), and -.050134 (trees). The trees' paired 95% block interval is
[-.235262, .162169]; **all three intervals include zero**. These descriptive
intervals use 1,000 circular moving-block resamples of eight meetings. Few policy
cycles, model selection and regime changes limit inference; the intervals do not
establish an independent-cycle sample size or a reliable future advantage.

| Model | Ordinary cut calls correct / 6 | False cut calls | Cut-cost-2 calls correct / 6 | False cut calls under cost rule |
|---|---:|---:|---:|---:|
| Frequency | 0 | 0 | 0 | 0 |
| Logistic | 0 | 0 | 1 | 0 |
| Trees | 3 | 1 | 4 | 1 |

The expanded trees' ordinary accuracy is 19/26. The separate cost-sensitive
decision rule reaches 20/26 and catches 4/6 cuts with one false alarm. Its
probabilities and probability scores are unchanged. Logistic still misses every
cut under argmax despite its better overall probability score than frequency.
These results do not solve rare-cut forecasting.

## Dependence on 2001

Eight of the ten added cuts occur in 2001; the other two are in 2002 and 2003.
They should not be interpreted as ten independent easing episodes. Keep all
early rows in the main experiment and report the prespecified sensitivity:
remove the eight 2001 scheduled decisions from training examples while retaining
the actual policy history in later features, unchanged test dates and the
expanded model's selected settings.

| Model | Brier with 2001 ↓ | Brier without 2001 ↓ |
|---|---:|---:|
| Frequency | .636944 | .653825 |
| Logistic | .507742 | .527859 |
| Trees | .424813 | .458433 |

Without the 2001 training examples, trees catch 2/6 cuts under argmax and 3/6
under the cost rule, with one false cut alarm under either rule. The Brier
difference is +.033621, with block interval [-.001538, .064929]. This measures
sensitivity to those training labels with fixed settings; it is neither a
causal effect nor independent confirmation across additional cycles.

## Artifacts and reproduction

- [Expanded run](runs/extended_2000-b4a00efeac35/complete.json), [2006 control](runs/extended_2000_control2006-c1d9ad9b9b02/complete.json), [2001 sensitivity](runs/extended_2000_no2001-44f28545c1f2/complete.json).
- [Comparison table](extended_2000/history_comparison.csv), [cut diagnostics](extended_2000/history_cut_diagnostics.csv), [paired differences](extended_2000/history_paired_differences.csv).
- [Data-quality audit](extended_2000/data_quality_audit.json), [year/class counts](extended_2000/coverage_by_year.csv), [feature missingness](extended_2000/feature_missingness.csv).
- [Probability plot](runs/extended_2000-b4a00efeac35/probabilities.png), [calibration plot](runs/extended_2000-b4a00efeac35/calibration.png), [largest errors](runs/extended_2000-b4a00efeac35/largest_errors.csv).

Each new run freezes its actual input panel and its SHA-256 digest, including
the cohort with 2001 removed. The independent verifier uses each run's own
training cohort and checks it against feature lineage and sourced labels.

```sh
export UV_CACHE_DIR="$PWD/.cache/uv"
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
export LOKY_MAX_CPU_COUNT=1
uv run --frozen rates snapshot --config configs/extended_2000.yaml --offline
uv run --frozen rates panel --config configs/extended_2000.yaml --offline
uv run --frozen python scripts/compare_history.py
uv run --frozen pytest -q
uv run --frozen python scripts/verify_outputs.py
```

Initial downloads require the locally configured FRED key; omit `--offline` for
a fresh cache. All **51 tests**, Ruff and independent artifact checks pass.
The expanded probability/calibration plots were visually inspected. The early
snapshot exposed an all-missing announcement-time timezone edge case; it is
fixed by preserving a UTC schema without inventing publication times and covered
by a synthetic regression test. No world-model implementation, trading or
external publication occurred.
