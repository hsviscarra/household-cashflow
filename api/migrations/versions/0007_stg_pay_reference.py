"""stg.stg_transaction.pay_reference (F5): the payer's label, e.g. "August" on a salary.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stg_transaction",
        sa.Column("pay_reference", sa.Unicode(100), nullable=True),
        schema="stg",
    )


def downgrade() -> None:
    op.drop_column("stg_transaction", "pay_reference", schema="stg")
