"""Staged category source (F23, ADR-022): stg.stg_transaction.category_source records that a
person chose a line's category on the statement's page ("manual" or "suggestion"), so the loaded
line says so instead of "by rule".

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stg_transaction",
        sa.Column("category_source", sa.Unicode(12), nullable=True),
        schema="stg",
    )


def downgrade() -> None:
    op.drop_column("stg_transaction", "category_source", schema="stg")
