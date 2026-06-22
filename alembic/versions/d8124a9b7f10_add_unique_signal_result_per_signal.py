"""add one tracking result per signal

Revision ID: d8124a9b7f10
Revises: 9ceb9fbc13bd
Create Date: 2026-06-22
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d8124a9b7f10"
down_revision: Union[str, Sequence[str], None] = "9ceb9fbc13bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("signal_results") as batch_op:
        batch_op.create_unique_constraint(
            "uq_signal_result_signal_id",
            ["signal_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("signal_results") as batch_op:
        batch_op.drop_constraint("uq_signal_result_signal_id", type_="unique")
