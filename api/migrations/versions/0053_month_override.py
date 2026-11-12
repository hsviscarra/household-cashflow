"""A line can be told which month it counts in (ADR-089): `core.transaction.month_override`.
When set it wins over the rule that works `cash_month` out (ADR-084), so a yearly bonus paid on
the 23rd counts in its own month while the salaries keep counting in the month they pay for.
Nullable, no backfill: no line has an override until a person sets one.

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transaction", sa.Column("month_override", sa.Date(), nullable=True), schema="core"
    )


def downgrade() -> None:
    # Lines moved by hand go back to the month the rule gives them at their next change.
    op.drop_column("transaction", "month_override", schema="core")
