# TradeSentinel

Educational, AI-assisted crypto **signal** system for BTC/USDT. It generates a
deterministic regime signal (BUY / HOLD / CASH), persists it, tracks its forward result,
and lets you ask an assistant about your own track record.

> ⚠️ **Educational use only. Not financial advice.** TradeSentinel **recommends and
> explains** signals — it **never executes trades** or manages capital. No guaranteed
> returns. The strategy is **not** approved for real-money use.

🇪🇸 [Léeme en español](README.es.md)

## Honest status

Running unattended since 2026-06-22. Real reconstructed equity, fees included:

| | |
|---|---|
| Strategy | **+15.9%** |
| Buy & hold BTC | **+28.5%** |
| Difference | **−12.5 pp** |

**The strategy is behind the market.** It is a *drawdown protector*, not a return
generator: in the walk-forward test period (a bear market) it beat buy & hold on 5/5
assets by ~32 pp; in the live period (a bull market) it lags. Same property, two regimes.

**12 strategy families have been tested** (regime, trend, mean reversion, momentum
rotation, vol-targeting, funding-rate carry, across crypto and 10 diversified ETFs).
None produces reliable absolute returns. The only one that did — funding-rate carry —
turned out to be decaying: its rate fell 4x in two years and is now below risk-free.

That conclusion is the project's main asset. The infrastructure reliably tells you when
something *doesn't* work, which is most of the time.

## How it works

```
market data (ccxt) → indicators → regime rules → signal (BUY/HOLD/CASH)
        → persist (Supabase) → forward tracking → Telegram alert
                             → LLM opinion logged (observer, never decides)
```

- **Deterministic first.** Technical rules (EMA/RSI regime on 4h, executed on 1h, no
  lookahead) decide the action. Validated config: `entry=2, exit=2, exit_buffer=0.02`.
- **The LLM never decides.** It explains signals and answers questions. Its opinion on
  each signal is recorded *without* affecting the action, so its value can be measured
  forward — an LLM cannot be validated backwards, since its training already contains
  the future of any historical candle.
- **Single source of truth.** The same strategy code in `app/core/` powers both the live
  API and the backtests, so what is served equals what was validated.

## The assistant

A read-only agent answers questions about the project and your own record. It uses
tools for every number (it never computes them itself) and full-text search over the
project's own documentation.

```
/preguntar cómo voy frente a comprar y mantener
/preguntar por qué se descartó el apalancamiento
```

Four non-negotiable rules: always cite the source, always state sample size, never
predict prices or give personalised advice, and say "I don't know" when it cannot back a
claim. A 30-question evaluation battery checks this automatically —
`python -m app.jobs.run_assistant_eval`.

## Tech stack

Python 3.12 · FastAPI · ccxt · Supabase (HTTPS) · APScheduler · python-telegram-bot ·
Groq · SQLAlchemy + Alembic (schema only) · pytest.

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
cp .env.example .env           # then fill in the values
```

## Run

```bash
# Local API + read-only dashboard (http://127.0.0.1:8000/dashboard)
uvicorn app.main:app --reload

pytest

# Backtests, from the repo root
python -m backtest.run_multi_asset_walk_forward   # the validation harness
python -m backtest.run_btc_regime_v2_no_lookahead # where the live config came from
```

`backtest/` deliberately holds only four files. Concluded studies are deleted once their
conclusion is recorded in `docs/ai-context/DECISIONS.md`; the code stays in git history.
Infrastructure is kept, experiments are not.

## Scheduled capture (free, serverless)

A GitHub Actions cron (`.github/workflows/capture.yml`) runs `python -m app.jobs.capture`
every 2h: it backfills missed candles, captures the current signal, evaluates pending
results, records the LLM opinion, and sends a Telegram alert. No always-on server needed.

A separate heartbeat (`heartbeat.yml`, every 6h) watches for a stalled capture, holes in
the record, and sustained AI-logging failures — each of which has happened at least once.

Required repo secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GROQ_API_KEY`, and
optionally `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. The runner uses KuCoin
(`EXCHANGE_ID=kucoin`) because Binance geoblocks GitHub's IPs; backtests use Binance.

## Project context

`docs/ai-context/` (local, not versioned) holds the authoritative state, every decision
with its reasoning, the roadmap, and the assistant plan.
