"""add signal_ai_opinions

Registro forward-only de opiniones del LLM sobre señales ya decididas. La tabla
es un observador: nada de la ruta de decisión la lee.

Revision ID: a3f71c4e9b02
Revises: d8124a9b7f10
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a3f71c4e9b02"
down_revision: Union[str, Sequence[str], None] = "d8124a9b7f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signal_ai_opinions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=False),
        # ok | rejected | error — los fallos se guardan a propósito: su
        # frecuencia mide la fiabilidad del LLM bajo la barrera interpretativa.
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("reasoning", sa.String(), nullable=True),
        sa.Column("risk_notes", sa.String(), nullable=True),
        sa.Column("error_reason", sa.String(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id", name="uq_signal_ai_opinion_signal_id"),
    )
    op.create_index(
        op.f("ix_signal_ai_opinions_signal_id"),
        "signal_ai_opinions",
        ["signal_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_signal_ai_opinions_signal_id"),
        table_name="signal_ai_opinions",
    )
    op.drop_table("signal_ai_opinions")
