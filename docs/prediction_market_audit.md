# Small prediction-market history audit

Follow-up: the [2026-10-31 source audit](market_baseline_sources.md) resolves legacy
identifiers and expands this original sample. A
[computed market benchmark](../reports/market_baseline_results.md) now compares ten
Kalshi and six reviewed Polymarket forecasts with frozen trees. The findings below
preserve the original, narrower audit and are not the current coverage assessment.

Public read-only endpoints tested 2026-10-30. Raw JSON responses are cached with
retrieval metadata; full contract wording is in
`data/processed/market_contract_audit.parquet`. A compact quote inventory is in
`reports/market_coverage.csv`, with access results in `reports/market_access.json`.

## Kalshi

Official [historical market metadata](https://docs.kalshi.com/api-reference/historical/get-historical-markets)
and [historical candlesticks](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks)
support archived contracts through `external-api.kalshi.com/trade-api/v2`.
The sample `KXFEDDECISION-25SEP` returns five settled contracts: hikes of 25 bp
or more than 25 bp, unchanged, cuts of 25 bp or more than 25 bp.

For the September 17, 2025 meeting, issuance is September 10 at 22:00 UTC.
The hourly candle ending at that cutoff supplies bid/ask for all five contracts;
one has no trade-close price. C25 settled Yes. Candle close values are recovered
without account credentials. **Candle-end age is zero; actual quote-update age
is unknown.** An unchanged candle can contain an older quote.

`KXFEDDECISION-24SEP` returns an empty market list. This is an exact finding for
that identifier and endpoint, not proof that no 2024 Fed contracts existed.
Discovering legacy series identifiers remains future audit work.

The returned rules assert mutual exclusivity but not a universally exhaustive
three-class partition: a 25-bp grid assumption is needed to exclude nonstandard
small changes. Some rendered primary-rule strings omit a comparison symbol
present in the title. Rules also treat cancelled meetings as an unchanged outcome
for later contracts; our cancelled meetings have no target. These require explicit
reconciliation before comparisons. No automatic normalization is performed.

## Polymarket

Gamma's `events?slug=fed-interest-rates-september-2024` returns event **11696**,
with contracts **504069–504072**. Full descriptions, Yes/No outcomes, token IDs,
and final outcome prices were recovered. Contract 504069 (50+ bp decrease)
has a final Yes price of 1. Resolution-source metadata is blank, although the
textual rules name the FOMC announcement. This audit records the metadata-derived
resolution; it does not independently audit the on-chain resolution process.

The official [CLOB price-history endpoint](https://docs.polymarket.com/api-reference/markets/get-prices-history)
returns token-specific history. At the September 11, 2024 22:00 UTC cutoff,
the last hourly samples were 21:00:02 UTC (sample age about one hour). Prices for
50+ bp cut, 25 bp cut, unchanged, and 25+ bp hike were 0.08, 0.89, 0.02, 0.0025.
Their sum is 0.9925; it is retained as observed, never normalized into a
three-class distribution. The endpoint does not supply historical bid, ask, or
interval volume; these remain null. Event lifetime volume is not substituted.

Definitions reference the **upper bound** immediately before versus after the
meeting. Our midpoint change agrees in direction for unchanged-width ranges,
but is a different general target. The hike description also contains the
contradictory word “below” and needs resolution-rule clarification. Non-25-bp
changes leave gaps in the listed buckets, and no-statement rules differ from
our cancellation treatment. Candidate class mappings are not certified matches.

## Use and limitations

The sample demonstrates that historical metadata and cutoff price samples can
be recovered. It does **not** justify a trading simulation: quotes may be stale,
market depth, fills, fees, and historical trading eligibility are not reconstructed.
No orders, wallets, brokerage integrations, or purchases exist in this project.

Any later forecasting comparison must use compatible targets, a verified
exclusive/exhaustive partition, only prices at or before issuance, explicit quote
age, and matching meeting coverage. Preserve ambiguous/missing outcomes instead
of repairing them by assumption. Do not make the macro benchmark depend on this
shorter history. Platform redistribution permissions remain unaudited; data stay local.

The Fed's [Kalshi and the Rise of Macro Markets](https://www.federalreserve.gov/econres/feds/kalshi-and-the-rise-of-macro-markets.htm)
motivates studying market-based expectations, but is not evidence that these
particular contract sets or quote samples are comparable or executable.
