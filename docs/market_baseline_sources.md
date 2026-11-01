# Market-implied probability source audit

Audited 2026-10-31 (Pacific time). Public read-only retrievals are cached locally.
The [benchmark protocol](market_benchmark_plan.md) and
[computed comparison](../reports/market_baseline_results.md) separate source
availability, target assumptions and forecasting performance.

## Source choices

| Source | What it measures | Historical access established | Cost/access and principal limit |
|---|---|---|---|
| CME FedWatch end-of-day API | Distribution over target ranges inferred from 30-Day Fed Funds futures | Documentation starts forecasts on January 27, 2014 for the January 28, 2015 meeting; first meeting is 2015, not 2014 | Advertised from $25/month; entitled OAuth credentials required. No purchase or authenticated retrieval performed. |
| CME FedWatch intraday API | 60-second updates of the same model-implied probabilities | Official documentation says history starts November 1, 2025 | Requires a separate entitlement; not a replacement for intraday history throughout our 2022–2025 test. |
| Raw fed funds futures | Contract-month average effective overnight rate expectation, subject to risk pricing | No licensed historical contract-price dataset acquired here | Reconstructing decision probabilities requires assumptions and a verified price timestamp; realized FRED rates do not substitute. |
| Kalshi `KXFED` | Binary upper-target-rate threshold contracts after a specified meeting | 402 archived market records across 40 event identifiers, July 2021–July 2026; the 26 test meetings have only 10 usable paired cutoff snapshots under our rule | Public historical metadata/candles retrieved without credentials. Hourly bid/ask snapshots exist, but history can be missing or stale. |
| Kalshi `KXFEDDECISION` | Buckets for the change at a scheduled meeting | 140 archived market records across 28 event identifiers, May 2023–July 2026; legacy tickers use `FEDDECISION-*` | Available metadata is useful, but listed bins assume a grid and cancellation rules changed. Not the primary price conversion in this run. |
| Polymarket Gamma + CLOB | Event metadata and per-outcome Yes-token price samples | Fed-rates tag query returned 86 closed events before 2026, including 14 candidate scheduled-decision events from May 2024–December 2025. Six May–December 2025 partitions pass the present rule review | Public read-only endpoints work without credentials. CLOB history supplies prices and timestamps, not historical executable bid/ask. |

These inventory counts describe the cached responses, not a completeness claim
about all contracts ever listed. The `KXFED` series filter returns legacy `FED-*`
events; requesting the legacy series filter alone returned no rows. Likewise,
an empty `KXFEDDECISION-24SEP` event query did not establish absence of a 2024
market: its actual identifier is `FEDDECISION-24SEP`.

## CME: the longer-history candidate

CME's [product page](https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html)
advertises the end-of-day entry price and extended history. The
[forecast specification](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457224472)
gives the first reporting/meeting dates and `/forecasts` fields: meeting date,
reporting date and range probabilities. Always specify both meeting and reporting
date; requesting only a meeting retrieves its latest forecast, which would leak
future information into our historical cutoff. Null probabilities must remain
missing unless the vendor defines their meaning explicitly.

The [end-of-day access documentation](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457320466)
requires entitled OAuth API access and states updates occur at 01:45 UTC on
business days. That is after the prior US evening's 18:00 New York issuance.
The `reportingDt` day label alone is not sufficient evidence of availability:
use the latest previously published snapshot, or obtain a verified historical
publication/calculation timestamp. Confirm the vendor's reporting-date convention
and holiday schedule before implementing that mapping.

The [intraday documentation](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/1054343170)
states a November 1, 2025 history start. The linked pricing PDF is dated November
2025 and some fees expired in May 2026; it does not establish today's price for
our automated research use. The advertised $25 entry price is not a verified
all-in licensing quote. Confirm the appropriate entitlement before buying anything.

The free [FedWatch user guide](https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html)
describes historical charts and Excel downloads for selected meetings with a
one-year lookback. That is a useful manual source, but this audit did not verify
a free machine-readable archive covering all 2015–2025 meetings.

## What futures imply, and what they do not identify

Under the [CME methodology](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html),
Fed Funds futures prices reflect the expected contract-month average effective
rate; `100 - futures price` is the corresponding implied rate. Calendar weights
separate pre/post-meeting portions. Its probability construction assumes 25-bp
increments and a proportional effective-rate response. This is an inferred
distribution, not a directly observed physical probability.

An expected rate alone cannot uniquely determine cut/hold/hike probabilities.
For example, 100% hold and a 50/50 equal-sized cut/hike mixture have the same
expected change. Converting futures or OIS rates to three classes therefore
needs restrictions or additional distributional information. Options can supply
such information in principle, with further contract/coverage issues. We did
not manufacture probabilities from a Treasury yield or today's revised FRED data.

Rate levels after a meeting also include possible intervening emergency moves.
They match a scheduled-meeting change only under an explicit mapping assumption.
The point of the baseline is to measure market predictive information empirically;
prices need not equal calibrated real-world frequencies because of risk premia,
spreads, liquidity and contract details.

## Public prediction-market endpoints and restrictions

Kalshi's [historical markets](https://docs.kalshi.com/api-reference/historical/get-historical-markets)
and [historical candlesticks](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks)
expose archived rules, strikes, results, quote OHLC, trade OHLC, volume and open
interest. Raw quote closes at/before the cutoff are retained. A candle end time
does not reveal when a standing quote was last updated. Zero bids can indicate
one-sided books; the resulting midpoint is a price proxy, not an executable trade.

Polymarket's [Gamma events](https://docs.polymarket.com/api-reference/events/list-events)
provide rule text, outcome/token mapping and final outcome prices; the
[CLOB price history](https://docs.polymarket.com/api-reference/markets/get-prices-history)
provides token-specific timestamp/price pairs. Current event `outcomePrices`
are settlement-era metadata and are never historical forecast inputs. The
current `/series/35` FOMC inventory omitted older closed events in our response;
tag discovery recovered them, illustrating why inventory methods matter.

Rules and contract membership retrieved today are retrospective metadata. We
freeze raw responses and exact reviewed rule hashes, but have not independently
reconstructed every historical amendment or on-chain resolution. Current public
access does not establish redistribution permission. Raw data and generated
datasets stay local and ignored by version control; no trading simulation,
orders, brokerage connection, wallet connection or external publication was added.

## Relevant research

[Diercks, Katz and Wright, *Kalshi and the Rise of Macro Markets*](https://www.federalreserve.gov/econres/feds/kalshi-and-the-rise-of-macro-markets.htm)
studies market-derived macro forecasts. Its [paper](https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf)
describes differencing threshold prices, handling stale/nonmonotone tails and
risk-neutral interpretation. Its favorable near-meeting findings are not our
seven-day classification accuracy. The linked accessible-materials ZIP contains
two HTML documents, not a raw trade-history dataset. The
[EconFutures website](https://econfutures.com/) still displays a launch placeholder
at this audit. No public raw dataset was obtained from that site or a paper-linked
GitHub release.

Next data step: retain the free matched benchmark, investigate older missing
Kalshi quotes/legacy rule versions, and obtain a CME end-of-day entitlement only
if the user chooses paid access. Add each source as a separate benchmark before
considering a model that learns to improve on market probabilities.
