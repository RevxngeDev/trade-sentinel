"""add knowledge_chunks

Base de conocimiento del asistente. Se ingesta SOLO en local
(`python -m app.jobs.ingest_knowledge`) porque `docs/ai-context/` está gitignored
y GitHub no puede leerlo — ver DECISIONS 2026-09-16.

Recuperación con full-text search de PostgreSQL: sin embeddings, sin dependencias
nuevas. Vectores solo si un set de evaluación demuestra que hace falta.

Revision ID: b5e2d81f4c73
Revises: a3f71c4e9b02
Create Date: 2026-09-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b5e2d81f4c73"
down_revision: Union[str, Sequence[str], None] = "a3f71c4e9b02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        # Fichero de origen, p.ej. DECISIONS.md — el asistente cita la fuente.
        sa.Column("source", sa.String(length=120), nullable=False),
        # Ruta de encabezados, p.ej. "Decisions > 2026-09-16 - Producto final".
        sa.Column("section", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        # Frescura: el asistente DEBE poder declarar la fecha de su conocimiento.
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_knowledge_chunk_hash"),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_source"), "knowledge_chunks", ["source"]
    )
    # Índice GIN para la búsqueda full-text. La expresión debe coincidir con la
    # que genera PostgREST al usar el operador `fts(spanish)`, o no se usará.
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_fts ON knowledge_chunks "
        "USING GIN (to_tsvector('spanish', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_fts")
    op.drop_index(op.f("ix_knowledge_chunks_source"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
