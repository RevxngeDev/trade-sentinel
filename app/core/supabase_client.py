"""Centralized HTTPS client for Supabase runtime persistence."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from supabase import Client, create_client

from app.config import settings

_client: Client | None = None


def get_supabase_client() -> Client:
    """Return the process-wide Supabase HTTP client."""
    global _client

    if _client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
            )
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    return _client


class SupabaseStore:
    """
    Base de los almacenes: cliente perezoso y paginación.

    Existía cuatro veces copiada (señales, resultados, opiniones, conocimiento)
    y el bucle de paginación dos. Al duplicarlo, un arreglo en uno no llegaba a
    los demás — que es justo como se coló el corte silencioso de PostgREST en
    `list_results` después de haberlo arreglado en `list_signals`.
    """

    # PostgREST corta en `max-rows` (1000 por defecto en Supabase) y NO avisa:
    # pedir 5000 devuelve 1000 en silencio. Por eso se pagina siempre.
    PAGE_SIZE = 1000

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        return self._client or get_supabase_client()

    async def paginate(
        self, fetch_page: Callable[[int, int], Any], limit: int
    ) -> list[Any]:
        """
        Acumula filas llamando a `fetch_page(offset, size)` hasta `limit`.

        Para en cuanto una página vuelve incompleta: eso significa que no queda
        nada más y seguir pidiendo sería gastar peticiones para nada.
        """
        rows: list[Any] = []
        while len(rows) < limit:
            size = min(self.PAGE_SIZE, limit - len(rows))
            response = await asyncio.to_thread(fetch_page, len(rows), size)
            rows.extend(response.data)
            if len(response.data) < size:
                break
        return rows
