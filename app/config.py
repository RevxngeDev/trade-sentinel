from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "TradeSentinel"

    exchange_id: str = "binance"

    default_symbol: str = "BTC/USDT"

    # Velas a descargar por timeframe (4h dirige el régimen, 1h la ejecución).
    ohlcv_limit: int = 600        # 4h
    ohlcv_exec_limit: int = 1000  # 1h

    # Config determinista validada para BTC/USDT (walk-forward 2026-06-21).
    # Candidato robusto: positivo en full/train/test y +18% agregado en los
    # 7 folds rolling. Ver docs/ai-context/DECISIONS.md.
    # La API en vivo usa EXACTAMENTE esta config (pipeline 4h->1h + máquina de
    # estado), para que la señal servida sea idéntica a la validada.
    entry_confirmation_bars: int = 2
    exit_confirmation_bars: int = 2
    exit_buffer_pct: float = 0.02
    cooldown_hours: int = 0
    min_hold_hours: int = 0

    # Timeframes de la estrategia de régimen.
    regime_base_timeframe: str = "4h"      # régimen
    regime_exec_timeframe: str = "1h"      # ejecución / exit buffer

    # El runtime NO usa SQLAlchemy: persiste vía supabase-py (HTTP). Estos URLs
    # son SOLO para Alembic (esquema/migraciones). Por defecto SQLite local.
    database_url: str = "sqlite:///./tradesentinel.db"
    # URL sync explícito para migraciones a Postgres (si se deja vacío se deriva
    # de database_url). Las migraciones a Supabase se aplican offline:
    # `alembic upgrade head --sql` y pegar en el SQL Editor.
    database_url_sync: str = ""

    # Runtime persistence uses the Supabase HTTPS API, not a PostgreSQL pooler.
    # The service-role key is backend-only and must never reach clients.
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Forward-only paper-trading tracking. A result is evaluated from the first
    # fully closed 1h candle at or after this horizon.
    tracking_horizon_hours: int = 4
    tracking_scan_limit: int = 500

    # Techo para métricas que reportan TOTALES (get_stats, performance). Debe
    # superar con holgura el histórico: si trunca, el total mostrado es falso.
    # A ~8 señales/día, 20000 cubre varios años.
    stats_scan_limit: int = 20000

    # AI interpretation is optional and never controls a signal action.
    groq_api_key: str = ""
    # 2026-09-09: Groq retiró toda la familia Llama; `llama-3.1-8b-instant` empezó
    # a devolver 404 y el registro de opiniones estuvo ~2 semanas guardando solo
    # errores. Verificado en vivo que este modelo responde y pasa las barreras
    # interpretativas. Los IDs de modelo de un proveedor CADUCAN: si vuelve a dar
    # 404, listar los disponibles con `client.models.list()` antes de elegir.
    groq_model: str = "openai/gpt-oss-20b"
    ai_max_retries: int = 2

    # Registro de opiniones del LLM por señal capturada EN VIVO (observador puro:
    # se guardan pero no tocan la decisión). Sirve para medir hacia adelante si la
    # IA aporta, ya que un LLM no se puede validar hacia atrás sin lookahead.
    # Off por defecto: consume cuota de Groq y hace red.
    ai_opinion_logging_enabled: bool = False

    # Telegram is disabled until a backend-only bot token is configured.
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Scheduler de captura de señales (paper trading 24/7).
    # Desactivado por defecto para no llamar a la red en dev/tests.
    # Cron por defecto: minuto 1 de cada 4ª hora UTC (tras el cierre de vela 4h).
    scheduler_enabled: bool = False
    scheduler_cron: str = "1 */4 * * *"

    # Backfill: al arrancar, rellenar las señales de fronteras 4h que falten
    # (p.ej. si el backend estuvo apagado). Idempotente (dedupe por vela).
    backfill_on_startup: bool = True
    backfill_lookback_days: int = 7

    # Dead-man's switch: si la última señal es más vieja que esto, la captura
    # probablemente se detuvo -> alerta.
    # Calibrado a 14h el 2026-08-26 tras 2 falsas alarmas: el cron de GitHub
    # Actions se retrasa (se observaron huecos de 9-14h) y el backfill lo cura
    # solo, así que 8h avisaba de algo que se arreglaba sin intervención. El
    # coste de detectar tarde es bajo (el backfill repara hasta 7 días atrás);
    # el de la fatiga de alertas es alto: se ignora el aviso que sí importa.
    heartbeat_max_age_hours: int = 14

    # Cuántas opiniones de IA recientes deben fallar SEGUIDAS para avisar. Alto
    # a propósito: un error suelto (timeout, rate limit) se recupera solo y
    # avisar de eso reintroduce la fatiga de alertas. Lo que hay que cazar es la
    # avería sostenida — p.ej. un ID de modelo retirado por el proveedor.
    heartbeat_ai_sample_size: int = 6

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
