"""Tests del servicio de conocimiento (con almacén falso, sin red)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.knowledge import KnowledgeSourceFreshness
from app.services.knowledge_service import DEFAULT_SOURCES, KnowledgeService

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, entries: list[KnowledgeSourceFreshness] | None = None) -> None:
        self.written: dict[str, list[dict]] = {}
        self.entries = entries or []

    async def replace_source(self, source: str, rows: list[dict]) -> int:
        self.written[source] = rows
        return len(rows)

    async def search(self, query: str, limit: int):
        return []

    async def freshness(self):
        return self.entries


def _corpus(tmp_path, **files: str):
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


# ============================================================
# Ingesta
# ============================================================


async def test_ingest_writes_chunks_per_source(tmp_path) -> None:
    corpus = _corpus(
        tmp_path,
        **{
            "DECISIONS.md": "# D\n\n## Una\n\ncuerpo uno\n\n## Dos\n\ncuerpo dos\n",
            "ROADMAP.md": "# R\n\n## Fase\n\ncontenido\n",
        },
    )
    store = FakeStore()

    result = await KnowledgeService(store).ingest(
        corpus, sources=["DECISIONS.md", "ROADMAP.md"]
    )

    assert result.sources == 2
    assert result.chunks == 3
    assert result.skipped == []
    assert len(store.written["DECISIONS.md"]) == 2
    assert store.written["ROADMAP.md"][0]["source"] == "ROADMAP.md"


async def test_missing_document_is_skipped_not_fatal(tmp_path) -> None:
    """Falta un doc: se omite y se informa, no se aborta toda la ingesta."""
    corpus = _corpus(tmp_path, **{"ROADMAP.md": "# R\n\ntexto\n"})
    store = FakeStore()

    result = await KnowledgeService(store).ingest(
        corpus, sources=["NO_EXISTE.md", "ROADMAP.md"]
    )

    assert result.skipped == ["NO_EXISTE.md"]
    assert result.sources == 1
    assert "ROADMAP.md" in store.written


async def test_rows_carry_citation_and_freshness_fields(tmp_path) -> None:
    """El asistente debe poder citar fuente y declarar la fecha."""
    corpus = _corpus(tmp_path, **{"DECISIONS.md": "# D\n\n## Sec\n\ncuerpo\n"})
    store = FakeStore()

    await KnowledgeService(store).ingest(corpus, sources=["DECISIONS.md"])

    row = store.written["DECISIONS.md"][0]
    assert row["source"] == "DECISIONS.md"
    assert row["section"] == "D > Sec"
    assert row["content_hash"]
    assert row["ingested_at"]


async def test_reingesting_replaces_instead_of_accumulating(tmp_path) -> None:
    """
    Una sección borrada del documento debe desaparecer del corpus. Con upsert
    quedaría huérfana y el asistente la citaría como vigente.
    """
    corpus = _corpus(tmp_path, **{"DECISIONS.md": "# D\n\n## A\n\nuno\n\n## B\n\ndos\n"})
    store = FakeStore()
    service = KnowledgeService(store)

    await service.ingest(corpus, sources=["DECISIONS.md"])
    assert len(store.written["DECISIONS.md"]) == 2

    (corpus / "DECISIONS.md").write_text("# D\n\n## A\n\nuno\n", encoding="utf-8")
    await service.ingest(corpus, sources=["DECISIONS.md"])

    assert len(store.written["DECISIONS.md"]) == 1
    assert store.written["DECISIONS.md"][0]["section"] == "D > A"


def test_session_log_is_not_ingested() -> None:
    """Diario cronológico: su contenido útil ya está destilado en los otros."""
    assert "SESSION_LOG.md" not in DEFAULT_SOURCES
    assert "DECISIONS.md" in DEFAULT_SOURCES
    assert "CURRENT_STATE.md" in DEFAULT_SOURCES


# ============================================================
# Frescura
# ============================================================


async def test_age_uses_the_oldest_document() -> None:
    """
    Si solo se reingestó un documento, el resto sigue caducado: el asistente no
    debe presumir de estar al día por el más reciente.
    """
    store = FakeStore(
        [
            KnowledgeSourceFreshness(source="A.md", chunks=1, ingested_at=NOW),
            KnowledgeSourceFreshness(
                source="B.md", chunks=1, ingested_at=NOW - timedelta(days=30)
            ),
        ]
    )

    age = await KnowledgeService(store).knowledge_age_days(now=NOW)

    assert age == pytest.approx(30.0, abs=0.01)


async def test_age_is_none_when_corpus_is_empty() -> None:
    age = await KnowledgeService(FakeStore([])).knowledge_age_days(now=NOW)

    assert age is None
