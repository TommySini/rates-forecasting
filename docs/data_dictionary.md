# Data dictionary

All analytical tables are Parquet. Calendar dates are ISO strings; timestamps are
timezone-aware UTC. Nulls are preserved. Rates are percentage points, e.g. 5.25;
rate changes are basis points. The source versions and calendar conventions are
defined in `point_in_time_policy.md`.

| Table | Key | Contents |
|---|---|---|
| `data/interim/meeting_inventory.parquet` | `meeting_id` | Calendar inventory since 1994, including scheduled, unscheduled, cancelled and non-policy sessions. Start/scheduled decision/actual decision dates; actual publication and conservative label-availability timestamps; effective date where explicit; before/after single target or range; midpoint change; class; sources, raw cache ID, parse status, reviewed evidence. |
| `data/interim/observations.parquet` | series, period, vintage start | Reference period, value, units, vintage interval, whether its start is a query bound, publication time (null if unknown), permitted availability, source URL/cache ID, retrieval time, method. |
| `data/processed/panel.parquet` | `meeting_id` | One seven-day forecast per primary scheduled decision; UTC issuance/target timestamps, target class, 19 candidate feature columns, quality flags, intervening emergency flag, lag, `data_kind=empirical`. Model input list excludes the two claims columns. |
| `data/processed/lineage.parquet` | meeting, feature | Feature value/formula/quality, maximum input availability, eligibility reason, JSON list of all contributing input values/periods/vintages/sources/timestamps. Missing JSON fields are null. |
| `data/processed/first_snapshot*.parquet` | meeting / feature | Audited July 2019 single-row panel and detailed lineage. |
| `data/processed/panel_lag2.parquet`, `lineage_lag2.parquet` | meeting / feature | Predeclared two-business-day availability sensitivity. |
| `reports/runs/*/predictions.parquet` | meeting, model | Issuance, actual class, model/version, training cutoff/count, probabilities in cut/hold/hike order; per-meeting Brier/log loss/accuracy. The run fingerprint binds input panel, source code, config and dependency lock. |
| `data/processed/market_contract_audit.parquet` | platform, contract | Event/contract/token IDs, question, full resolution rules, meeting and candidate class mapping, historical timestamp/price/bid/ask/volume where available, resolution, raw sources and mapping caveats. |

`verification_status=announcement_parsed` means a rule extracted an announced
target or applied a documented source review; it does not claim every record was
independently reviewed by a human. See `docs/meeting_verification.md` for spot checks.
Primary target timestamps may be null; **label availability** remains conservative
and explicit. Effective date is not substituted for either field.

Lineage `quality=observed` describes a usable numeric value, not certainty about
its release time. `availability_method` separately identifies exact announcement
times versus conservative vintage lags. Manually checked release times carry a
`publication_source_url`; other economic publication times remain null.

| Feature | Definition / units |
|---|---|
| policy_midpoint | Latest available announced single target or range midpoint, percent |
| previous_scheduled_bps | Last published scheduled decision's midpoint change, bp |
| days_since_policy_change | Calendar days since latest available change, including emergencies |
| cpi_yoy, core_cpi_yoy | 100 × (latest SA index / same month one year earlier − 1) |
| core_cpi_3m_ann | 100 × ((latest / three months earlier)^4 − 1) |
| payroll_1m | Latest less previous month's payrolls, thousands |
| payroll_3m_mean | (Latest less three months earlier)/3, thousands per month |
| unemployment | Latest SA unemployment rate, percent |
| unemployment_3m_change | Latest less three months earlier, percentage points |
| claims_4w_mean | Four consecutive weeks' mean initial claims, persons; audit-only |
| claims_4w_change_pct | Percent change from preceding four-week mean; audit-only |
| yield_3m, yield_2y, yield_10y | Latest eligible daily Treasury constant maturity yields, percent |
| slope_10y_2y | Same-reference-date 10y less 2y, percentage points |
| ip_3m_pct | 100 × (latest industrial production / three months earlier − 1) |
| macro_max_age_days, financial_max_age_days | Maximum age of latest available reference periods in each group |

Monthly reference dates are period starts; age therefore includes the elapsed
month plus release lag. Raw index bases are vintage-specific; ratios are computed
within the historical information set. Feature units differ deliberately and are
scaled inside the logistic training pipeline only.
