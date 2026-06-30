"""
Base declarativa de SQLAlchemy.

La persistencia en runtime usa `supabase-py` por HTTP (ver app/services/signal_store.py).
Los modelos (`app/models/`) y este `Base` existen únicamente como fuente del esquema
para Alembic. No hay engine ni sesiones SQLAlchemy en runtime.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
