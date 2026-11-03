"""Category descriptions (F23, ADR-022): core.category.description says what goes in each
category. The picker shows it and Claude's suggestions read it. Seeded categories get a drafted
description (seed v5) when theirs is empty; Hernan edits them in Settings.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.seeds import load_v5

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "category", sa.Column("description", sa.Unicode(400), nullable=True), schema="core"
    )
    if context.is_offline_mode():
        op.execute("-- seed v5 (category descriptions) is loaded only in online mode")
        return
    category = sa.table(
        "category",
        sa.column("category_id", sa.Integer),
        sa.column("parent_id", sa.Integer),
        sa.column("name", sa.Unicode(100)),
        sa.column("description", sa.Unicode(400)),
        schema="core",
    )
    load_v5(op.get_bind(), category)


def downgrade() -> None:
    op.drop_column("category", "description", schema="core")
