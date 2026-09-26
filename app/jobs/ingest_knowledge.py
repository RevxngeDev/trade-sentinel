"""
Ingesta LOCAL de la base de conocimiento del asistente.

Este job NO debe correr nunca en GitHub Actions: `docs/ai-context/` está
gitignored y el runner no puede verlo (DECISIONS 2026-09-16). Corre a mano
después de actualizar la documentación.

Uso:
    python -m app.jobs.ingest_knowledge
    python -m app.jobs.ingest_knowledge --status
    python -m app.jobs.ingest_knowledge --search "por que no se adopto vol-targeting"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from app.services.knowledge_service import DEFAULT_CORPUS_DIR, KnowledgeService

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def run_ingest(corpus_dir: Path) -> None:
    result = await KnowledgeService().ingest(corpus_dir)
    print(
        f"\nIngesta OK: {result.sources} documentos, {result.chunks} fragmentos "
        f"({result.ingested_at:%Y-%m-%d %H:%M} UTC)"
    )
    if result.skipped:
        print(f"Omitidos (no encontrados): {', '.join(result.skipped)}")


async def run_status() -> None:
    service = KnowledgeService()
    entries = await service.freshness()

    if not entries:
        print("Base de conocimiento VACIA. Corre la ingesta.")
        return

    print(f"\n{'documento':<24} {'fragmentos':>10}  ingestado")
    for entry in entries:
        print(f"{entry.source:<24} {entry.chunks:>10}  {entry.ingested_at:%Y-%m-%d %H:%M} UTC")

    age = await service.knowledge_age_days()
    print(f"\nAntiguedad del conocimiento mas viejo: {age:.1f} dias")


async def run_search(query: str) -> None:
    results = await KnowledgeService().search(query, limit=5)

    if not results:
        print("Sin resultados.")
        return

    for chunk in results:
        print(f"\n--- {chunk.source} > {chunk.section} ({chunk.ingested_at:%Y-%m-%d}) ---")
        print(chunk.content[:400])


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta local de la base de conocimiento.")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--status", action="store_true", help="Muestra frescura por documento.")
    parser.add_argument("--search", type=str, help="Prueba una búsqueda.")
    args = parser.parse_args()

    if args.status:
        asyncio.run(run_status())
    elif args.search:
        asyncio.run(run_search(args.search))
    else:
        asyncio.run(run_ingest(args.corpus_dir))


if __name__ == "__main__":
    main()
