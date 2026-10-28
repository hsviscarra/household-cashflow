"""Loan amortization tables (F14, ADR-014): core.loan_installment, one row per installment of a
loan holding, with what it pays and the balance after it.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)


def upgrade() -> None:
    op.create_table(
        "loan_installment",
        sa.Column("installment_id", sa.Integer(), primary_key=True),
        sa.Column(
            "holding_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.holding.holding_id",
                name="fk_loan_installment_holding_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("principal", MONEY, nullable=False),
        sa.Column("interest", MONEY, nullable=False),
        sa.Column("other", MONEY, nullable=False),
        sa.Column("total", MONEY, nullable=False),
        sa.Column("balance_after", MONEY, nullable=False),
        sa.Column("status", sa.Unicode(4), nullable=False),
        sa.CheckConstraint("status IN ('paid', 'due')", name="ck_loan_installment_status"),
        sa.UniqueConstraint("holding_id", "number", name="uq_loan_installment_holding_id"),
        schema="core",
    )
    op.create_index(
        "ix_loan_installment_holding_id", "loan_installment", ["holding_id"], schema="core"
    )


def downgrade() -> None:
    # The balances read from the tables go with them.
    op.execute("DELETE FROM [core].[balance_snapshot] WHERE [source] = 'amortization';")
    op.drop_index("ix_loan_installment_holding_id", table_name="loan_installment", schema="core")
    op.drop_table("loan_installment", schema="core")
