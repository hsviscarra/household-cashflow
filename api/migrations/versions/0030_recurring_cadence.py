"""Bills & subscriptions (ADR-031): how often a recurring item repeats and the day it's due.

every_months: 1 monthly (all existing rows), 2, 3, 4, 6 or 12; 0 once (only its first month).
due_day: the day of the month it's usually paid (1-31); empty = read from the lines it matched.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recurring_template",
        sa.Column("every_months", sa.Integer(), server_default="1", nullable=False),
        schema="core",
    )
    op.add_column("recurring_template", sa.Column("due_day", sa.Integer()), schema="core")
    op.create_check_constraint(
        "ck_recurring_template_every_months",
        "recurring_template",
        "every_months IN (0, 1, 2, 3, 4, 6, 12)",
        schema="core",
    )
    op.create_check_constraint(
        "ck_recurring_template_due_day",
        "recurring_template",
        "due_day IS NULL OR (due_day >= 1 AND due_day <= 31)",
        schema="core",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_recurring_template_due_day", "recurring_template", schema="core", type_="check"
    )
    op.drop_constraint(
        "ck_recurring_template_every_months", "recurring_template", schema="core", type_="check"
    )
    op.drop_column("recurring_template", "due_day", schema="core")
    # SQL Server named the column's default; drop it with the column.
    op.drop_column("recurring_template", "every_months", schema="core", mssql_drop_default=True)
