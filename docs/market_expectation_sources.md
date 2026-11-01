# Longer-history market expectations: source review

2026-10-31. Kalshi and Polymarket cover only about 2022–2025. The user asked for
market-implied expectations with longer history, to anchor a model on the market
and test corrections at several horizons. Nothing below has been downloaded yet.

Timing rule for every source: the price or response must exist **at or before the
model's issuance time** for that horizon (for example 18:00 New York seven days
before the decision). Sources measured just before the announcement answer a
different question and are not a fair baseline.

## Ranked sources

| Source | History | Meeting-specific? | Access | Fit |
|---|---|---|---|---|
| Fed funds futures (CME ZQ), by contract month | Oct 1988– | Yes, via the CME FedWatch / Kuttner day-weighting | Paid; likely via Stanford LSEG Workspace/Datastream (remote) or Bloomberg (in person, download caps) | **Best**: the standard market benchmark, any horizon |
| Treasury bills and short constant-maturity yields (DTB4WK, DGS1MO from 2001-07-31; DGS3MO, DGS6MO, DGS1 longer) | 2001– (1-month) | Indirect: average expected rate over the bill's life | Free (FRED/ALFRED) | **Usable now**; noisier |
| NY Fed Survey of Primary Dealers / Market Expectations | Results 2011– | Yes: probability of each target range after upcoming meetings | Free; published about 3 weeks after the meeting | Benchmark forecaster only, never a model input |
| SOFR futures and options; Atlanta Fed Market Probability Tracker | 2018– | Partly (quarterly contracts) | Paid data / Atlanta Fed tool | Short history |
| Eurodollar futures | 1981–2023 | No (3-month LIBOR) | Paid | Longer horizons; credit noise |
| SF Fed monetary-policy surprise databases | 1988– | Yes | Free | **Wrong timing**: minutes before the announcement |
| Minneapolis Fed market-based probabilities | 2007– (weekly) | No (Treasury yields 6–12 months ahead) | Free | Low relevance |

## Notes

**Fed funds futures.** Each monthly contract settles at 100 minus the average
effective fed funds rate for that month, so a meeting's expected change is read
from the day-weighted difference between contracts around it; FedWatch then maps
it to 25-bp outcome probabilities ([CME methodology](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html);
[Kuttner 2001](https://www.newyorkfed.org/research/staff_reports/sr99.html)).
Gürkaynak, Sack and Swanson (2007) find fed funds futures dominate bills, term
deposits and eurodollar instruments for forecasting policy out to six months
([paper](https://sites.socsci.uci.edu/~swanson2/papers/mbmmpe.pdf)). Needs every
contract month, not only a continuous front-month series. Daily settlement is
mid-afternoon Chicago time, before our 18:00 New York cutoff. Corrections needed:
where the effective rate sits inside the target range, the zero lower bound, and
risk premia, which grow with horizon (Piazzesi and Swanson 2008). Licensed data
must stay local and out of version control.

**Bills.** Same archive caveat as our yields: ALFRED vintages start in 2005, but
these series are essentially never revised. The 1-month bill matches the next
meeting more closely than the 3-month bill we use now. Distortions: debt-ceiling
episodes (2011, 2013, 2023, 2025), flight to safety, and supply changes.

**Dealer survey.** Questions go out about two weeks before each meeting; results
appear about three weeks after it ([NY Fed](https://www.newyorkfed.org/markets/market-intelligence/survey-of-market-expectations)).
The responses were formed before our seven-day cutoff but were not public then,
so they can be scored as a competing forecast, not used as an input. Recent data
are Excel; older years are mostly PDF.

**Surprise databases** ([SF Fed](https://www.frbsf.org/research-and-insights/data-and-indicators/monetary-policy-surprises/))
imply the expectation minutes before each announcement. Useful only to measure
how much the market learns during the final week, never as the seven-day baseline.

## Recommendation

1. Now, free: add the 1-month bill (2001–) beside the 3-month and 2-year spreads.
2. Main benchmark: fed funds futures by contract month, 1988–2025, exported by
   the user through Stanford's licensed access; compute meeting probabilities at
   1, 7, 30, 60 and 90 days before each decision with the CME method, validated
   against FedWatch and Kalshi where they overlap.
3. Score the dealer survey (2011–) as an additional forecaster.
