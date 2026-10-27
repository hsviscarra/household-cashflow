"""Recurring entries (F11, ADR-008): templates, their amount from a month on, one entry per
template and month, and the link from a transaction to the entry it pays.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)
TXN_TYPES = "'income', 'expense', 'savings', 'transfer', 'refund', 'fee_interest', 'debt_payment'"


def _stamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "recurring_template",
        sa.Column("template_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_recurring_template_category_id"),
            nullable=False,
        ),
        sa.Column("type", sa.Unicode(12), nullable=False),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("core.account.account_id", name="fk_recurring_template_account_id"),
            nullable=True,
        ),
        sa.Column("person", sa.Unicode(10), nullable=True),
        sa.Column("match_pattern", sa.Unicode(200), nullable=True),
        sa.Column("tolerance_pct", sa.Numeric(5, 2), server_default="10", nullable=False),
        sa.Column("start_month", sa.Date(), nullable=False),
        sa.Column("end_month", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.Unicode(10), nullable=False),
        sa.Column("excel_block", sa.Unicode(30), nullable=True),
        sa.Column("excel_group", sa.Unicode(100), nullable=True),
        sa.Column("excel_label", sa.Unicode(100), nullable=True),
        sa.Column("notes", sa.Unicode(400), nullable=True),
        *_stamps(),
        sa.CheckConstraint(f"type IN ({TXN_TYPES})", name="ck_recurring_template_type"),
        sa.CheckConstraint("source IN ('manual', 'excel')", name="ck_recurring_template_source"),
        sa.UniqueConstraint("name", name="uq_recurring_template_name"),
        schema="core",
    )
    op.create_table(
        "recurring_amount",
        sa.Column("amount_id", sa.Integer(), primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.recurring_template.template_id",
                name="fk_recurring_amount_template_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("from_month", sa.Date(), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.UniqueConstraint("template_id", "from_month", name="uq_recurring_amount_template_id"),
        schema="core",
    )
    op.create_table(
        "recurring_entry",
        sa.Column("entry_id", sa.Integer(), primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.recurring_template.template_id",
                name="fk_recurring_entry_template_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("is_override", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("status", sa.Unicode(8), server_default="planned", nullable=False),
        sa.Column("notes", sa.Unicode(400), nullable=True),
        *_stamps(),
        sa.CheckConstraint("status IN ('planned', 'skipped')", name="ck_recurring_entry_status"),
        sa.UniqueConstraint("template_id", "month", name="uq_recurring_entry_template_id"),
        schema="core",
    )
    op.create_index("ix_recurring_entry_month", "recurring_entry", ["month"], schema="core")
    op.add_column(
        "transaction", sa.Column("recurring_entry_id", sa.Integer(), nullable=True), schema="core"
    )
    op.create_foreign_key(
        "fk_transaction_recurring_entry_id",
        "transaction",
        "recurring_entry",
        ["recurring_entry_id"],
        ["entry_id"],
        source_schema="core",
        referent_schema="core",
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_transaction_recurring_entry_id", "transaction", ["recurring_entry_id"], schema="core"
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_recurring_entry_id", table_name="transaction", schema="core")
    op.drop_constraint(
        "fk_transaction_recurring_entry_id", "transaction", schema="core", type_="foreignkey"
    )
    op.drop_column("transaction", "recurring_entry_id", schema="core")
    op.drop_index("ix_recurring_entry_month", table_name="recurring_entry", schema="core")
    op.drop_table("recurring_entry", schema="core")
    op.drop_table("recurring_amount", schema="core")
    op.drop_table("recurring_template", schema="core")
