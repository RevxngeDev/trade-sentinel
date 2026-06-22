import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Raíz del proyecto en el path para poder importar `app`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app import models  # noqa: E402,F401  (registra la metadata)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# URL SYNC para migraciones. Usa database_url_sync si está definido (Postgres
# directo/Session pooler); si no, lo deriva de database_url quitando el driver
# async (sqlite+aiosqlite -> sqlite, postgresql+asyncpg -> postgresql/psycopg2).
sync_url = settings.database_url_sync or (
    settings.database_url.replace("+aiosqlite", "").replace("+asyncpg", "")
)
config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    configure_kwargs = {
        "target_metadata": target_metadata,
        "literal_binds": True,
        "dialect_opts": {"paramstyle": "named"},
    }

    # Runtime now uses Supabase HTTPS and therefore may not have a direct
    # PostgreSQL URL. Generate PostgreSQL DDL offline in that case.
    if settings.supabase_url and not settings.database_url_sync:
        context.configure(dialect_name="postgresql", **configure_kwargs)
    else:
        context.configure(url=url, **configure_kwargs)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite: permite ALTER en migraciones
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
