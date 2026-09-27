# TradeSentinel

Sistema educativo de **señales** de cripto para BTC/USDT, asistido por IA. Genera una
señal determinista de régimen (BUY / HOLD / CASH), la guarda, mide su resultado hacia
adelante, y te deja preguntarle a un asistente sobre tu propio historial.

> ⚠️ **Solo uso educativo. No es asesoramiento financiero.** TradeSentinel **recomienda y
> explica** señales — **nunca ejecuta operaciones** ni gestiona capital. Sin rentabilidad
> garantizada. La estrategia **no** está aprobada para dinero real.

🇬🇧 [Read me in English](README.md)

## Estado honesto

Funcionando solo desde el 2026-06-22. Equity real reconstruida, con comisiones:

| | |
|---|---|
| Estrategia | **+15,9%** |
| Comprar y mantener BTC | **+28,5%** |
| Diferencia | **−12,5 pp** |

**La estrategia va por detrás del mercado.** Es un *protector de caídas*, no un generador
de retorno: en el periodo de walk-forward (bajista) batió a comprar y mantener en 5 de 5
activos por ~32 puntos; en el periodo en vivo (alcista) se queda atrás. Es la misma
propiedad vista en dos regímenes distintos.

**Se han probado 12 familias de estrategia** (régimen, tendencia, reversión a la media,
rotación por momentum, vol-targeting y carry de funding, sobre cripto y sobre 10 ETFs
diversificados). Ninguna produce retorno absoluto fiable. La única que lo dio —el carry
de funding— resultó estar secándose: su tasa cayó 4 veces en dos años y hoy está por
debajo del activo sin riesgo.

Esa conclusión es el principal activo del proyecto. La infraestructura detecta con
fiabilidad cuándo algo *no* funciona, que es casi siempre.

## Cómo funciona

```
datos de mercado (ccxt) → indicadores → reglas de régimen → señal (BUY/HOLD/CASH)
        → guardar (Supabase) → seguimiento forward → alerta de Telegram
                             → opinión del LLM registrada (observa, no decide)
```

- **Primero lo determinista.** Las reglas técnicas (régimen EMA/RSI en 4h, ejecución en
  1h, sin lookahead) deciden la acción. Config validada:
  `entry=2, exit=2, exit_buffer=0.02`.
- **El LLM nunca decide.** Explica señales y responde preguntas. Su opinión sobre cada
  señal se registra *sin* afectar a la acción, para poder medir su valor hacia adelante:
  un LLM no se puede validar hacia atrás, porque su entrenamiento ya contiene el futuro
  de cualquier vela histórica.
- **Una sola fuente de verdad.** El mismo código de estrategia en `app/core/` alimenta la
  API en vivo y los backtests, así que lo que se sirve es idéntico a lo validado.

## El asistente

Un agente de solo lectura responde preguntas sobre el proyecto y tu propio historial.
Usa herramientas para cada número (nunca los calcula él) y busca en la documentación del
propio proyecto.

```
/preguntar cómo voy frente a comprar y mantener
/preguntar por qué se descartó el apalancamiento
```

Cuatro reglas innegociables: citar siempre la fuente, decir siempre el tamaño de muestra,
nunca predecir precios ni dar consejo personalizado, y decir "no lo sé" cuando no pueda
respaldar algo. Una batería de 30 preguntas lo comprueba automáticamente —
`python -m app.jobs.run_assistant_eval`.

## Tecnología

Python 3.12 · FastAPI · ccxt · Supabase (HTTPS) · APScheduler · python-telegram-bot ·
Groq · SQLAlchemy + Alembic (solo esquema) · pytest.

## Instalación

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
cp .env.example .env           # y rellena los valores
```

## Ejecución

```bash
# API local + panel de solo lectura (http://127.0.0.1:8000/dashboard)
uvicorn app.main:app --reload

pytest

# Backtests, desde la raíz del repo
python -m backtest.run_multi_asset_walk_forward   # el banco de pruebas
python -m backtest.run_btc_regime_v2_no_lookahead # de aquí salió la config en vivo
```

`backtest/` tiene solo cuatro ficheros a propósito. Los estudios concluidos se borran una
vez su conclusión queda en `docs/ai-context/DECISIONS.md`; el código permanece en el
histórico de git. La infraestructura se guarda, los experimentos no.

## Captura programada (gratis, sin servidor)

Un cron de GitHub Actions (`.github/workflows/capture.yml`) ejecuta
`python -m app.jobs.capture` cada 2 h: rellena las velas perdidas, captura la señal
actual, evalúa los resultados pendientes, registra la opinión del LLM y envía la alerta
de Telegram. No hace falta un servidor encendido.

Un vigilante aparte (`heartbeat.yml`, cada 6 h) detecta si la captura se detuvo, si hay
huecos en el registro o si la IA lleva tiempo fallando — las tres cosas han pasado al
menos una vez.

Secrets necesarios en el repo: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`GROQ_API_KEY` y, opcionalmente, `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. El runner usa
KuCoin (`EXCHANGE_ID=kucoin`) porque Binance geobloquea las IPs de GitHub; los backtests
usan Binance.

## Contexto del proyecto

`docs/ai-context/` (local, no versionado) contiene el estado autoritativo, cada decisión
con su razonamiento, el roadmap y el plan del asistente.
