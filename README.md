# Rates Forecasting Model

Offline research on seven-day probabilities of the next scheduled Federal Reserve
decision: **cut, hold, or hike**. The initial implementation uses small baselines
and an auditable historical information set. No trading or brokerage integration.

Implemented: official-calendar/announcement ingestion, cached ALFRED vintage
histories, UTC point-in-time feature lineage, chronological model selection and
evaluation, saved probabilities/metrics/plots, dependence-aware uncertainty,
availability/emergency sensitivities, and a separate prediction-market audit.

**Actual coverage:** meeting inventory 1994–2025; 207 sourced scheduled labels in
2000–2025; primary macro panel **2006–2025, 159 meetings** (118 holds, 24 hikes,
17 cuts). Training/development/holdout contain 56/48/55 meetings. Treasury vintage
coverage determines the narrower primary start. Claims are excluded from the
17-feature model because their vintage archive starts in 2009.

Start with [the run report](reports/baseline_results.md),
[first snapshot](reports/snapshot_2019-07-31.md), and
[source audit](docs/source_inventory.md).

The subsequent [cut-sensitive experiment](docs/cut_sensitive_experiment.md) uses
the requested chronological 75% / 12.5% / 12.5% split (119/20/20 meetings), a full
55-candidate search across four development folds, and explicit cut-error costs.
Run it with `uv run --frozen rates evaluate --config configs/cut_sensitive.yaml --offline`.
It preserves the original benchmark and is exploratory because the historical
test period has already been examined. Its development period contains no cuts.
See [computed results](reports/cut_sensitive_results.md), including cut recall,
false alarms and comparison with the original settings on the same test meetings.

The [extended 2000–2025 experiment](docs/extended_2000.md) adds all 48 already
labeled 2000–2005 meetings, giving **207 meetings and 27 cuts**. It uses 12
policy/macro features with reliable vintage coverage; Treasury yields remain in
the separate original benchmark. Its split is 155/26/26 and development includes
three 2019 cuts. Data and audits live in separate `extended_2000` directories.
Run the snapshot and panel with `--config configs/extended_2000.yaml`, then
`uv run --frozen python scripts/compare_history.py` for the expanded model,
matched 2006-start control and sensitivity excluding 2001 training labels.
The [expanded-history results](reports/extended_2000_results.md) report the
matched comparison, the 2001 sensitivity and uncertainty.

## Reproduce

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.15 (pinned; uv can install Python).
Run from this repository root. Dependencies are fully pinned in `uv.lock`.

```sh
export UV_CACHE_DIR="$PWD/.cache/uv"
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
export LOKY_MAX_CPU_COUNT=1
uv sync --frozen
```

For downloads, put `FRED_API_KEY=...` in a local `.env` or export it privately.
Use `.env.example` as a template **without overwriting an existing `.env`**.
Obtain a free key from [FRED](https://fred.stlouisfed.org/docs/api/api_key.html).
Never commit or share the key. Raw requests/metadata redact it.

```sh
uv run --frozen rates sources
uv run --frozen rates meetings
uv run --frozen rates snapshot
# Inspect reports/snapshot_2019-07-31.md and docs/snapshot_review.md first.
uv run --frozen rates panel
uv run --frozen rates evaluate
uv run --frozen rates sensitivity
uv run --frozen rates markets
uv run --frozen pytest -q
uv run --frozen python scripts/verify_outputs.py
```

The checked-in snapshot review records the initial audit. `rates panel` requires
a validated snapshot artifact. Downloads resume from an immutable hash-checked
cache; a missing key raises an explicit error with no revised-data fallback.
For this workspace, all needed raw data are already cached:

```sh
uv run --frozen rates all --offline
uv run --frozen python scripts/verify_outputs.py
uv run --frozen ruff check src tests scripts
```

`--offline` forbids downloads and needs no key when the exact raw requests are
cached. A fresh clone needs the download sequence or a private copy of the raw
cache. Data/cache/model artifacts are deliberately excluded from version control;
small reports, source annotations, code, tests and the lockfile remain reviewable.

## Outputs

| Location | Contents |
|---|---|
| `data/raw/` | Original HTTP bytes, public parameters, UTC retrieval time and SHA-256 |
| `data/interim/` | Meeting inventory and economic vintage observations |
| `data/processed/` | Primary/sensitivity panels, detailed lineage, first snapshot, market contract audit |
| `reports/` | Source/coverage/missingness/exclusions, snapshot audit, verification and evaluation history |
| `reports/runs/<variant>-<fingerprint>/` | Immutable selected settings, per-meeting predictions, model comparison, class/period results, calibration, paired uncertainty, largest errors and PNG plots |

Exact run paths and computed scores are in [baseline_results.md](reports/baseline_results.md).
Identical completed runs are reused. Changed evaluations are logged as exploratory;
do not keep tuning on the historical holdout while calling it untouched.

## Conventions and limitations

Issue at 18:00 America/New_York seven calendar days before the scheduled decision,
rolling back federal holidays/weekends. Store UTC with proper daylight saving.
Unknown intraday economic-release times receive a full business-day lag, including
financial series. Targets use announced policy targets/ranges, never effective
funds rates. Emergency changes are separate events; cancelled meetings remain
visible in the exclusions ledger, without invented labels.

The primary panel has five missing feature cells, retained and imputed only inside
training fits. Eighty early decision publication times remain unknown; conservative
label availability is separate from actual publication. Retrospective calendars
and incomplete historical archives remain limitations. The 55-meeting holdout
contains only nine cuts and eleven hikes; calibration and comparative uncertainty
are correspondingly weak. Public market samples need rule reconciliation before
being treated as comparable probability distributions.

See [point-in-time rules](docs/point_in_time_policy.md),
[data dictionary](docs/data_dictionary.md),
[announcement checks](docs/meeting_verification.md),
[decisions](docs/decisions.md), and
[market audit](docs/prediction_market_audit.md).
The [research plan](docs/research_plan.md) designs a small probabilistic state-space
extension and a later PSI-inspired experiment; neither is implemented yet.
