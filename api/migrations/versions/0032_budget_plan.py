"""A monthly budget per spending group (ADR-039): an amount from a month on, optionally rolling
unspent (or overspent) money into the next month.

core.budget_plan: one row per group and the month it starts; the amount for a month is the row
with the latest start on or before it. Amount 0 = no budget from that month.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budget_plan",
        sa.Column("budget_plan_id", sa.Integer(), primary_key=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_budget_plan_category_id"),
            nullable=False,
        ),
        sa.Column("start_month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("rollover", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_by", sa.Unicode(320), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("category_id", "start_month", name="uq_budget_plan_category_id"),
        sa.CheckConstraint("amount >= 0", name="ck_budget_plan_amount"),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("budget_plan", schema="core")
