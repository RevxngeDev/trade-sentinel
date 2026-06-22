"""
Capa de base de datos: engine + sesión async de SQLAlchemy 2.

El URL es configurable (SQLite async por defecto; PostgreSQL+asyncpg en prod).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _connect_args(url: str) -> dict:
    # asyncpg + pooler de Supabase: desactivar el cache de prepared statements
    # evita el error de pgBouncer. Inofensivo en conexión directa/SQLite.
    if "asyncpg" in url:
        return {"statement_cache_size": 0}
    return {}


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"future": True, "connect_args": _connect_args(url)}

    # En Postgres (Supabase) limitamos el pool: el Session pooler del plan Free
    # admite máx. 15 conexiones. Con esto la app nunca lo agota. pre_ping y
    # recycle evitan usar conexiones que el pooler ya cerró. SQLite no aplica.
    if not url.startswith("sqlite"):
        kwargs.update(
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    return kwargs


engine = create_async_engine(settings.database_url, **_engine_kwargs(settings.database_url))

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia de FastAPI: una sesión async por request."""
    async with async_session_factory() as session:
        yield session


async def init_models() -> None:
    """
    Crea las tablas (dev/tests). En producción se usa Alembic.
    Importa los modelos para registrar la metadata antes de crear.
    """
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
