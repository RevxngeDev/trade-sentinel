# TradeSentinel

Educational, AI-assisted crypto **signal** agent for BTC/USDT. It analyzes the market,
generates a deterministic regime signal (BUY / HOLD / CASH) with an explanation, persists
it, and tracks its forward result for paper trading.

> ⚠️ **Educational use only. Not financial advice.** TradeSentinel **recommends and
> explains** signals — it **never executes trades** or manages capital. No guaranteed
> returns. The strategy is **not** approved for real-money use.

## How it works

```
market data (ccxt) → indicators → regime rules → signal (BUY/HOLD/CASH)
        → persist (Supabase) → forward tracking → optional Telegram alert
                                                 → optional AI explanation
```

- **Deterministic first.** Technical rules (EMA/RSI regime on 4h, executed on 1h, no
  lookahead) decide the action. Validated config: `entry=2, exit=2, exit_buffer=0.02`.
- **The LLM only interprets.** It can explain a stored signal (confidence, reasoning,
  risk notes) but never chooses actions, predicts prices, or creates entry/exit levels.
- **Single source of truth.** The same strategy code in `app/core/` is used by both the
  live API and the backtests, so what is served equals what was validated.

It is a **defensive, low-frequency** strategy with a small edge. See
`docs/ai-context/` (local) for the full state, decisions and roadmap.

## Tech stack

Python 3.12 · FastAPI · ccxt · Supabase (HTTPS) · APScheduler · python-telegram-bot ·
Groq (optional) · SQLAlchemy + Alembic (schema only) · pytest.

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

# Tests
pytest

# Backtests (run from repo root)
python -m backtest.run_btc_regime_signal_audit_no_lookahead
python -m backtest.run_btc_regime_v2_no_lookahead
```

## Scheduled capture (free, serverless)

A GitHub Actions cron (`.github/workflows/capture.yml`) runs `python -m app.jobs.capture`
every 4h: it backfills missed candles, captures the current signal, evaluates pending
results, and sends a Telegram alert. No always-on server required.

Required repo secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and (optional)
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. The runner uses KuCoin (`EXCHANGE_ID=kucoin`)
because Binance geoblocks GitHub's IPs; backtests/validation use Binance.

## Status

Strategy validation done; the system is in **controlled paper-trading data collection**.
This is measurement only — not proof of profitability and not production approval.
