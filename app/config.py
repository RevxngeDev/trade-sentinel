from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "TradeSentinel"
    environment: str = "development"

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

    min_confidence: int = 65

    # Base de datos (runtime, async). Por defecto SQLite local (dev/tests).
    # En producción/Supabase: postgresql+asyncpg://... (vía .env).
    database_url: str = "sqlite+aiosqlite:///./tradesentinel.db"

    # URL SYNC para migraciones Alembic (Postgres -> psycopg2). Si se deja
    # vacío se deriva de database_url. En Supabase apuntar a la conexión que
    # uses (recomendado: Session pooler, puerto 5432).
    database_url_sync: str = ""

    # Scheduler de captura de señales (paper trading 24/7).
    # Desactivado por defecto para no llamar a la red en dev/tests.
    # Cron por defecto: minuto 1 de cada 4ª hora UTC (tras el cierre de vela 4h).
    scheduler_enabled: bool = False
    scheduler_cron: str = "1 */4 * * *"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()