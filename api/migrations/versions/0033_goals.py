"""Saving goals (ADR-040): a target amount, an optional date, where the money is kept (a bank
account or a balance-sheet item) or an amount saved typed by hand, and a planned monthly amount.

Revises 0032 (budget). Revision ID: 0033
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goal",
        sa.Column("goal_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("target_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("target_date", sa.Date()),
        sa.Column("item_key", sa.Unicode(40)),
        sa.Column("saved_amount", sa.Numeric(19, 4)),
        sa.Column("monthly_amount", sa.Numeric(19, 4)),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Unicode(400)),
        sa.Column("created_by", sa.Unicode(320), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target_amount > 0", name="ck_goal_target"),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("goal", schema="core")
