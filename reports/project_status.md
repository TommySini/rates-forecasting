# Project status: where we are and what comes next

Written 2026-10-31. A plain-language summary of the whole project so far: what
exists, what we learned, where we are stuck, and the next steps with owners.
Detailed reports are linked at the end.

## 1. The goal

Predict the probability that the Fed **cuts, holds or hikes** at its next
scheduled meeting, using only information available at the time of the forecast.
The longer-term idea is a "world model": a model that understands how the economy
evolves and uses that to forecast the Fed, ideally better than prediction markets
(Kalshi, Polymarket) at some horizon. No trading code exists or is planned yet.

## 2. What has been built

**Data (all point-in-time: every number is what was actually known that day).**

- Fed decisions: every scheduled meeting 2000–2025 labeled from official Fed
  statements; emergency moves handled separately.
- Economic data from ALFRED's archive of past data versions: CPI, core CPI,
  payrolls, unemployment, industrial production. Revisions are respected.
- Treasury yields (3-month, 2-year, 10-year; 1-month in one variant). Before
  June 2005 the archive is missing, so pre-2005 values are taken as unrevised
  (checked: yields change in at most 0.05% of archived cases, and two test weeks
  match the Fed's original 2001 releases exactly).
- **Main dataset: 207 meetings, Feb 2000–Dec 2025: 140 holds, 40 hikes, 27 cuts.**
- Split by time: 155 training meetings (to May 2019), 26 for tuning (to Sept
  2022), **26 test meetings (Nov 2022–Dec 2025: 14 holds, 6 hikes, 6 cuts)**.
- Market prices (built by Codex): Kalshi for 10 of the 26 test meetings,
  Polymarket for 6, taken at the same moment as our forecasts.

**Checks.** Every forecast refits using only decisions known before that
meeting. Independent verifier scripts recheck timestamps, scores and saved
forecasts; 74 automated tests pass. Each experiment's plan was written down
before its test scores were computed.

## 3. Results so far

All forecasts are made **7 days before** each decision. Brier score: lower is
better; 0 is perfect, about 0.64 is "always guess the historical average".

**On the same 26 test meetings:**

| Model | What it uses | Brier | Cuts caught (of 6) |
|---|---|---:|---:|
| Historical frequency | nothing | 0.637 | 0 |
| Logistic regression (retired) | 12 economic/policy inputs | 0.508 | 0 |
| World-model pilot (Codex) | 2 hidden economy factors + logistic | 0.510 | 0 |
| Boosted trees, no yields | 12 inputs | 0.425 | 3 |
| Boosted trees, with yields | 17 inputs | 0.432 | 3 |
| Taylor-rule ordered model | 7 numbers, textbook rule | 0.343 | 4 |
| "Repeat last move" ordered model | 3 numbers | 0.343 | 4 |
| **Market-spread ordered model (best)** | last move + 3-month and 2-year yield spreads, 5 numbers | **0.252** | 3 (0 false alarms) |
| Same + 1-month bill | 6 numbers | 0.285 | 3 |

**At turning points** (14 meetings right after a hold, including the three that
broke a pause): market-spread model 0.198, "repeat last move" 0.362, trees 0.42.
For the September 2024 first cut it gave 47% (others about 10%).

**Against prediction markets, on the meetings where they have prices:**

| Meetings | Kalshi | Polymarket | Our best model | Trees with yields |
|---|---:|---:|---:|---:|
| 10 with Kalshi prices | **0.035** | — | 0.320 | 0.393 |
| 6 with both (2025) | 0.006 | **0.004** | 0.318 | 0.292 |

Market prices were checked to come from the same moment as our forecasts
(quotes at most two hours earlier, never later).

## 4. What we learned

1. **Fewer, well-chosen parameters beat bigger models.** Tuning pushed every
   flexible model toward its most restricted settings; 207 meetings can't
   support many learned numbers.
2. **The Taylor rule itself did not help.** Deliberately wrong economic starting
   values scored the same; the gain came from the Fed's habit of repeating its
   last move, which bigger models had squashed.
3. **Market yields are the strongest signal we have**, especially at turning
   points. But the 3-month yield is largely the market's own forecast, so this
   model mostly reads traders' expectations.
4. **The 1-month bill adds noise**: the May 2023 debt-ceiling standoff distorted
   it and caused most of its loss.
5. **Markets are about 10 times more accurate one week ahead.** It's not a
   timing trick: by then the Fed has finished signaling (its quiet period starts
   about 11 days before each decision), and traders price Fed speeches, minutes,
   press conferences and news that our model never sees.
6. Codex's post-hoc audit found the trees were tuned with a different refitting
   schedule than they are tested with; matching them changes the chosen settings
   ([diagnosis](market_gap_diagnosis.md)).

## 5. Where we are stuck

- **One week ahead, beating markets is not realistic** with economic data alone;
  the answer is largely announced in advance.
- **Too few events.** 27 cuts and about 10 real turning points since 2000. The 26
  test meetings have been reused across experiments, so every historical result
  is exploratory; small differences are not proof.
- **The best long-history market data is not yet in hand.** Fed funds futures
  (1988–today) are the standard way markets price each meeting, and they would
  give about 300 meetings of market forecasts at any horizon. They need a
  licensed source (Stanford LSEG Workspace or Bloomberg).
- **The economy world model hasn't added value yet.** The first pilot improved
  economic-data forecasts but not Fed forecasts.

## 6. Next steps

| # | Step | Owner | Why |
|---|---|---|---|
| 1 | Ask the Stanford GSB library for daily settlement prices of every 30-day fed funds futures contract, 1988–2025 (message text in section 8) | **You** | Unlocks a proper 37-year market benchmark |
| 2 | Build the market-spread model at **1 week, 1 month, 2 months and 3 months** before each meeting, using daily yields | Claude | Shows where markets are still unsure, which is the only place an economic edge can exist |
| 3 | Market-anchored model: start from the market forecast, let economic trends (inflation, jobs, unemployment) make a small correction; test at each horizon | Claude | Can't do worse than the market; tells us if economics adds anything |
| 4 | When futures arrive: convert to meeting probabilities (the CME FedWatch method), check against Kalshi/FedWatch, rerun steps 2–3 | Claude | Replaces the rough yield stand-in |
| 5 | Self-learning economy model: learns trends from about 128 monthly series (FRED-MD, 1959–) plus yields by predicting next month's data, feeding the small Fed model | Claude | The world model, aimed only at horizons where step 3 shows room |
| 6 | Simulated economies: pre-train the step-5 model on thousands of simulated booms, recessions and turning points, then fine-tune on real data, with wrong-simulator controls | Claude | Real history has few turning points |
| 7 | Forward forecast log: record a forecast before every upcoming Fed meeting | Both | The only clean test left; historical test years are used up |
| 8 | Housekeeping: commit the current work to git (about 65 files changed or new since the last commit); coordinate so Claude and Codex don't work in the same folder at once | You | Protects the work; avoids collisions |

Skipped on purpose: fake data generated by our own model, oversampling cuts,
AI-chatbot-simulated Fed meetings and off-the-shelf forecasting AIs for
historical tests (they either add no information or have seen the answers).

## 7. Where to find things

| Topic | Plan | Results |
|---|---|---|
| Original benchmark (2006–2025) | [decisions](../docs/decisions.md) | [baseline_results.md](baseline_results.md) |
| 2000–2025 extension | [extended_2000.md](../docs/extended_2000.md) | [extended_2000_results.md](extended_2000_results.md) |
| World-model research | [world_model_research.md](../docs/world_model_research.md) | — |
| World-model pilot (Codex) | [world_model_pilot.md](../docs/world_model_pilot.md) | [world_model_results.md](world_model_results.md) |
| Taylor-rule model | [structured_policy_model.md](../docs/structured_policy_model.md) | [policy_model_results.md](policy_model_results.md) |
| Yields + market-spread model | [extended_2000_yields.md](../docs/extended_2000_yields.md) | [yields_results.md](yields_results.md) |
| 1-month bill | [extended_2000_bills.md](../docs/extended_2000_bills.md) | [bills_results.md](bills_results.md) |
| Market prices (Codex) | [market_benchmark_plan.md](../docs/market_benchmark_plan.md) | [market_baseline_results.md](market_baseline_results.md), [market_gap_diagnosis.md](market_gap_diagnosis.md) |
| Longer-history market sources | [market_expectation_sources.md](../docs/market_expectation_sources.md) | — |

Best-model run: `reports/policy_model_runs/24f35e51a919`. Reproduction commands
are in the [README](../README.md) and each results file.

## 8. Message for the Stanford library

Send through the GSB library's Ask Us form:

> I need daily settlement prices for every CBOT/CME 30-Day Federal Funds futures
> contract month, including expired contracts, from 1988 to 2025, for academic
> research. Which Stanford resource (LSEG Workspace/Datastream or Bloomberg) has
> this, and how can I bulk-export it?

Save the export (columns: trade date, contract month, settlement price, and
volume/open interest if available) in `data/raw/`, which is kept out of git.
Stanford's license is for academic use only; delete the data when the project ends.
