# Rates Forecasting Model

A research project testing whether **economic world modeling** can improve
forecasts of Federal Reserve decisions.

Before each scheduled FOMC meeting, the model gives the probability of a
**cut, hold or hike**, using only information that was public at that moment.
Forecasts are compared with simple statistical models and with prediction
markets (Kalshi, Polymarket).

**Status report:** [shareable page](https://app.superset.sh/page/fed-decision-forecasting-i305pt)
· [markdown version](reports/project_status.md)

## The idea

Fed decisions are rare: 207 scheduled meetings since 2000, only 27 of them cuts.
That is too little data for a large model to learn from directly. Economic data,
on the other hand, is plentiful: decades of monthly releases. The plan is to
learn how the economy evolves from that abundant data, and keep the part that
maps the economy to a Fed decision small.

> **Hypothesis:** learning shared economic dynamics and reusable structure can
> improve policy forecasts with limited labeled decisions, compared with direct
> supervised prediction.

Inspired by [World Modeling with Probabilistic Structure Integration](https://arxiv.org/abs/2509.09737),
without assuming its results carry over to macroeconomics. A negative result
still leaves a clean dataset and a reproducible benchmark.

## What the system does

| Goal | Status |
|---|---|
| Rebuild the information available before every meeting (2000–2025) | Done |
| Predict cut/hold/hike probabilities 7 days before each decision | Done |
| Evaluate in time order against simple baselines | Done |
| Compare with Kalshi and Polymarket prices | Done, small samples |
| Test economic world models and structure integration | In progress |

No trading or brokerage code. All results are research, not advice.

## Where things stand

Brier score on the same 26 test meetings (Nov 2022–Dec 2025); lower is better.

| Model | Brier |
|---|---:|
| Last Fed move + Treasury yield spreads (5 parameters) | **0.252** |
| Repeat the last move (3 parameters) | 0.343 |
| Boosted trees (12–17 inputs) | 0.425–0.432 |
| First world-model pilot | 0.510 |
| Historical frequency | 0.637 |

On the 10 meetings with Kalshi prices: **Kalshi 0.035**, our best model 0.320.

- Small, structured models beat larger ones on this little data.
- Market yields are the strongest signal, especially before turning points.
- One week out, markets are far ahead: the Fed has already signaled its decision.

## Next steps

1. Forecast 1–3 months ahead, where markets are less certain.
2. Start from the market forecast and let an economy model correct it.
3. Add fed funds futures (1988–today) as the long-history market benchmark.
4. Build the self-learning economy model, pre-trained on simulated economies.
5. Keep a live forecast log for upcoming meetings.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is installed automatically).

```sh
uv sync --frozen
cp -n .env.example .env # add a free FRED_API_KEY; never commit .env
uv run --frozen rates all          # download data, build panels, run baselines
uv run --frozen pytest -q
uv run --frozen python scripts/verify_outputs.py
```

Once the raw data is cached, add `--offline` to rerun without network access.
Each experiment's plan lists its own commands.

## Experiments

| Experiment | Plan | Results |
|---|---|---|
| Baselines, 2006–2025 | [decisions](docs/decisions.md) | [baseline_results](reports/baseline_results.md) |
| Extended history, 2000–2025 | [extended_2000](docs/extended_2000.md) | [results](reports/extended_2000_results.md) |
| World-model pilot | [world_model_pilot](docs/world_model_pilot.md) | [results](reports/world_model_results.md) |
| Taylor-rule reaction model | [structured_policy_model](docs/structured_policy_model.md) | [results](reports/policy_model_results.md) |
| Treasury yields (best model) | [extended_2000_yields](docs/extended_2000_yields.md) | [results](reports/yields_results.md) |
| 1-month bill | [extended_2000_bills](docs/extended_2000_bills.md) | [results](reports/bills_results.md) |
| Prediction markets | [market_benchmark_plan](docs/market_benchmark_plan.md) | [results](reports/market_baseline_results.md) |

Background: [research plan](docs/research_plan.md),
[world-model research](docs/world_model_research.md),
[market data sources](docs/market_expectation_sources.md).

## How the data is handled

- Each forecast is made at 6 p.m. New York time, seven days before the decision.
- Economic data comes from [ALFRED](https://alfred.stlouisfed.org/), which keeps
  every past version of each release, so later revisions never leak backwards.
- Decisions come from official Fed statements; emergency moves are tracked separately.
- Models are refit before every test meeting using only decisions already announced,
  and each experiment's success test is written down before it is scored.

Details: [point-in-time rules](docs/point_in_time_policy.md) ·
[data dictionary](docs/data_dictionary.md) · [source inventory](docs/source_inventory.md).

## Layout

```
configs/   experiment settings
docs/      plans, data rules, decisions
src/       data ingestion, features, models, evaluation
scripts/   experiment runners and verifiers
tests/     automated tests (synthetic data only)
reports/   results and audits (run outputs stay local)
data/      downloaded and processed data (not in git)
```
