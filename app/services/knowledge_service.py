"""
Ingesta y consulta de la base de conocimiento del asistente.

Ingesta SOLO LOCAL: `docs/ai-context/` está gitignored, así que GitHub no puede
leer estos documentos (DECISIONS 2026-09-16). Si algún día aparece un job de
ingesta en Actions, está mal por construcción.

Contrapartida aceptada: el corpus se queda rancio si no se reingesta. Por eso
cada fragmento guarda `ingested_at` y el asistente DEBE declarar la fecha de su
conocimiento en cada respuesta.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.knowledge import split_markdown
from app.schemas.knowledge import (
    IngestionRunRead,
    KnowledgeChunkRead,
    KnowledgeSourceFreshness,
)
from app.services.knowledge_store import KnowledgeStore, SupabaseKnowledgeStore

logger = logging.getLogger(__name__)

DEFAULT_CORPUS_DIR = Path("docs/ai-context")

# SESSION_LOG queda fuera a propósito: es un diario cronológico enorme cuyo
# contenido útil ya está destilado en DECISIONS y CURRENT_STATE. Ingerirlo
# llenaría la búsqueda de versiones viejas de hechos ya superados.
DEFAULT_SOURCES = [
    "CURRENT_STATE.md",
    "DECISIONS.md",
    "ARCHITECTURE.md",
    "ROADMAP.md",
    "COMMANDS.md",
    "ASSISTANT_PLAN.md",
    "PROJECT_CONTEXT.md",
]


class KnowledgeService:
    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self.store = store or SupabaseKnowledgeStore()

    async def ingest(
        self,
        corpus_dir: Path = DEFAULT_CORPUS_DIR,
        sources: list[str] | None = None,
    ) -> IngestionRunRead:
        names = sources if sources is not None else DEFAULT_SOURCES

        total_chunks = 0
        ingested_sources = 0
        skipped: list[str] = []

        for name in names:
            path = corpus_dir / name
            if not path.exists():
                skipped.append(name)
                logger.warning("Documento no encontrado, se omite: %s", path)
                continue

            chunks = split_markdown(path.read_text(encoding="utf-8"), source=name)
            rows = [
                {
                    "source": chunk.source,
                    "section": chunk.section[:500],
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                    "char_count": chunk.char_count,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
                for chunk in chunks
            ]

            written = await self.store.replace_source(name, rows)
            total_chunks += written
            ingested_sources += 1
            logger.info("%s -> %d fragmentos", name, written)

        return IngestionRunRead(
            sources=ingested_sources,
            chunks=total_chunks,
            skipped=skipped,
            ingested_at=datetime.now(timezone.utc),
        )

    async def search(self, query: str, limit: int = 5) -> list[KnowledgeChunkRead]:
        return await self.store.search(query, limit)

    async def freshness(self) -> list[KnowledgeSourceFreshness]:
        return await self.store.freshness()

    async def knowledge_age_days(self, now: datetime | None = None) -> float | None:
        """
        Antigüedad del fragmento MÁS VIEJO, en días.

        Se usa el más viejo, no el más nuevo: si solo se reingestó un documento,
        el conocimiento del resto sigue caducado y el asistente no debe presumir
        de estar al día.
        """
        entries = await self.freshness()
        if not entries:
            return None

        now = now or datetime.now(timezone.utc)
        oldest = min(entry.ingested_at for entry in entries)
        return (now - oldest).total_seconds() / 86400
