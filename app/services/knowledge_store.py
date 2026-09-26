"""Persistencia de la base de conocimiento por HTTPS (supabase-py)."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.schemas.knowledge import KnowledgeChunkRead, KnowledgeSourceFreshness


class KnowledgeStore(Protocol):
    async def replace_source(
        self, source: str, rows: list[dict[str, Any]]
    ) -> int: ...

    async def search(self, query: str, limit: int) -> list[KnowledgeChunkRead]: ...

    async def freshness(self) -> list[KnowledgeSourceFreshness]: ...


class SupabaseKnowledgeStore:
    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        return self._client or get_supabase_client()

    async def replace_source(self, source: str, rows: list[dict[str, Any]]) -> int:
        """
        Sustituye TODOS los fragmentos de un fichero.

        Borrar y reinsertar en vez de upsert por hash: así desaparecen las
        secciones que se hayan eliminado del documento. Un upsert dejaría
        fragmentos huérfanos de decisiones ya borradas, y el asistente los citaría
        como vigentes.
        """

        def write() -> Any:
            self.client.table("knowledge_chunks").delete().eq("source", source).execute()
            if not rows:
                return None
            return self.client.table("knowledge_chunks").insert(rows).execute()

        response = await asyncio.to_thread(write)
        return len(response.data) if response is not None and response.data else 0

    async def search(self, query: str, limit: int) -> list[KnowledgeChunkRead]:
        def fetch() -> Any:
            # `limit()` va ANTES de `text_search()`: el builder que devuelve el
            # filtro de texto no expone `limit`.
            return (
                self.client.table("knowledge_chunks")
                .select("*")
                .limit(limit)
                .text_search("content", query, options={"config": "spanish"})
                .execute()
            )

        response = await asyncio.to_thread(fetch)
        return [KnowledgeChunkRead.model_validate(item) for item in response.data]

    async def freshness(self) -> list[KnowledgeSourceFreshness]:
        def fetch() -> Any:
            return (
                self.client.table("knowledge_chunks")
                .select("source,ingested_at")
                .order("ingested_at", desc=True)
                .limit(5000)
                .execute()
            )

        response = await asyncio.to_thread(fetch)

        by_source: dict[str, dict[str, Any]] = {}
        for row in response.data:
            entry = by_source.setdefault(
                row["source"], {"chunks": 0, "ingested_at": row["ingested_at"]}
            )
            entry["chunks"] += 1
            # La consulta viene ordenada desc: la primera es la más reciente.
        return [
            KnowledgeSourceFreshness(
                source=source,
                chunks=data["chunks"],
                ingested_at=data["ingested_at"],
            )
            for source, data in sorted(by_source.items())
        ]
