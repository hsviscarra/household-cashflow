"""Reference tables: core.account, core.category, core.merchant_rule (F1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "account",
        sa.Column("account_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("institution", sa.Unicode(100), nullable=False),
        sa.Column("kind", sa.Unicode(20), nullable=False),
        sa.Column("owner", sa.Unicode(10), nullable=False),
        sa.Column("country", sa.Unicode(2), nullable=False),
        sa.Column("last4", sa.Unicode(4), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('checking', 'savings', 'credit_card')", name="ck_account_kind"
        ),
        sa.CheckConstraint("owner IN ('Hernan', 'Lauren', 'Joint')", name="ck_account_owner"),
        sa.CheckConstraint("country IN ('US', 'EC')", name="ck_account_country"),
        sa.UniqueConstraint("name", name="uq_account_name"),
        schema="core",
    )
    op.create_table(
        "category",
        sa.Column("category_id", sa.Integer(), primary_key=True),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_category_parent_id"),
            nullable=True,
        ),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("kind", sa.Unicode(10), nullable=False),
        sa.Column("color", sa.Unicode(7), nullable=True),
        sa.Column("is_fixed", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('income', 'expense', 'savings', 'transfer')", name="ck_category_kind"
        ),
        sa.UniqueConstraint("parent_id", "name", name="uq_category_parent_id"),
        schema="core",
    )
    op.create_table(
        "merchant_rule",
        sa.Column("rule_id", sa.Integer(), primary_key=True),
        sa.Column("pattern", sa.Unicode(200), nullable=False),
        sa.Column("match_type", sa.Unicode(12), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_merchant_rule_category_id"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), server_default=sa.text("50"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "match_type IN ('contains', 'starts_with', 'regex')",
            name="ck_merchant_rule_match_type",
        ),
        schema="core",
    )
    op.create_index("ix_merchant_rule_priority", "merchant_rule", ["priority"], schema="core")


def downgrade() -> None:
    op.drop_index("ix_merchant_rule_priority", table_name="merchant_rule", schema="core")
    op.drop_table("merchant_rule", schema="core")
    op.drop_table("category", schema="core")
    op.drop_table("account", schema="core")
