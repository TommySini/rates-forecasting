# Source audit (2026-10-30)

Machine-readable observed coverage is in `reports/series_coverage.csv`. Its earliest
vintage is an archive boundary, **not proof that every observation/revision since
that date is complete**. Actual usable coverage is checked again in the panel.

| Source / identifiers | Definition / units / frequency | Revisions and coverage | Availability and access |
|---|---|---|---|
| [Fed calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), [historical archive](https://www.federalreserve.gov/monetarypolicy/fomc_historical.htm) | Scheduled meetings and intermeeting actions; event frequency | Inventory 1994–2025; primary verified announcement labels 2000–2025. Early statements may omit numerical levels or holds. Retrospective calendar corrections possible. | Public HTML, no key. Use explicit announcement time when stated; otherwise leave publication time null and permit use next US federal business day at 18:00 ET. Never infer policy from effective funds rates. |
| [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL) | Headline CPI-U, seasonally adjusted index; monthly | Seasonal revisions; observed vintage archive begins 1972-07-21. | FRED v1 key; ALFRED date + one business day at 18:00 ET. No assumed intraday time. |
| [CPILFESL](https://fred.stlouisfed.org/series/CPILFESL) | CPI-U excluding food/energy, seasonally adjusted index; monthly | Seasonal revisions; vintage archive begins 1996-12-12. | Same. Index-base metadata can differ by vintage; derive within the historical information set. |
| [PAYEMS](https://fred.stlouisfed.org/series/PAYEMS) | Total nonfarm payroll employment, thousands of persons, SA; monthly | Monthly revisions and annual benchmarks; vintages from 1955-05-06. | Same. Derived growth uses contemporaneously revised prior months. |
| [UNRATE](https://fred.stlouisfed.org/series/UNRATE) | Civilian unemployment rate, percent, SA; monthly | Seasonal adjustments/population changes; vintages from 1960-03-15. | Same. |
| [ICSA](https://fred.stlouisfed.org/series/ICSA) | Initial unemployment insurance claims, persons, SA; weekly ending Saturday | Weekly/seasonal revisions; **vintages only from 2009-05-28** in audit. | Same. Collected for audit; excluded from primary models to preserve common history. |
| [DGS3MO](https://fred.stlouisfed.org/series/DGS3MO), [DGS2](https://fred.stlouisfed.org/series/DGS2), [DGS10](https://fred.stlouisfed.org/series/DGS10) | Treasury constant maturity yields (3m, 2y, 10y), percent, NSA; business daily | Corrections possible; all vintage archives begin **2005-06-28**. Long observation history is not long vintage history. | Same ALFRED date + one business day rule, even for financial data. Do not use the observation date as release date. JSON requests chunked to respect the 2,000-vintage limit. |
| [INDPRO](https://fred.stlouisfed.org/series/INDPRO) | Industrial production, SA index; monthly | Revisions/rebasing; vintages from 1927-01-26. | Same; use within-vintage ratios, no assumed modern index base. |
| [BLS employment archive](https://www.bls.gov/news.release/archives/empsit_07052019.htm), [CPI archive](https://www.bls.gov/news.release/archives/cpi_07112019.htm) | Original releases, dates and embargo times | Manually cross-check July 2019 snapshot. 224k payroll gain and 3.7% unemployment agree. | Public, no key; direct scripted BLS access returned HTTP 403 here; browser research access succeeded. ALFRED remains reproducible primary input. |
| [FRED API v1](https://fred.stlouisfed.org/docs/api/fred/), [observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), [vintagedates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html) | Versioned observations and archive coverage | Explicit real-time intervals, pagination and immutable raw responses. The API also has v2 bulk functionality; v1 is sufficient here. | Free registered `FRED_API_KEY` in local environment or `.env`; never logged. API access tested successfully. |
| [Kalshi historical candles](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks) | Contract-specific historical OHLC prices, bid/ask candles, volume | Small settled Fed sample; archived and live datasets have different endpoints. | Read-only public endpoints tested; see `reports/market_coverage.csv`. Historical candles are not executable order-book snapshots. |
| [Polymarket price history](https://docs.polymarket.com/api-reference/markets/get-prices-history) | Token-specific timestamp/price history | Gamma metadata and CLOB histories tested separately; empty history is not zero price. | Public read-only calls, no wallet or trading API. Bid/ask and time-specific volume not supplied by this price endpoint. |

Actual observation start/end dates, titles, units, frequencies, and archive date
counts are recorded from the live API, separately from our requested sample.

Original Fed/BLS/BEA/DOL/Treasury US government data are generally publicly
available; source-specific exceptions and attribution requirements still apply.
[FRED terms](https://fred.stlouisfed.org/legal/) also govern API use and third-party
series. Do not assume a FRED key grants unrestricted redistribution. This project
keeps raw data and analytical datasets local and out of Git. Kalshi/Polymarket
data redistribution rights were not granted or independently adjudicated by this
audit; no bulk republication is performed.

The [ALFRED methodology](https://alfred.stlouisfed.org/help) uses source release
dates, provider dates, or first FRED availability when a source date is unknown.
The extra business day is a conservative operational convention, not a guarantee
that archive metadata never contain historical errors. Sensitivity adds a second day.

Core PCE and retail sales are deferred: the initial model already has inflation
and activity measures, and adding sources requires a separate vintage audit.

The later [2000–2025 extension](extended_2000.md) uses the five monthly series
with suitable earlier vintage coverage, alongside policy history. All 48 added
2000–2005 meetings have complete values for its 12 selected features. It excludes
Treasury/claims features throughout the extended sample. A January 2001 snapshot
was checked against original BLS and Fed releases before scaling; the BLS
publication time is recorded without relaxing the conservative availability lag.
