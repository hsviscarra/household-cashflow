"""Monthly report (F16, ADR-015): core.monthly_report, one saved report per month with its facts
and findings.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monthly_report",
        sa.Column("report_id", sa.Integer(), primary_key=True),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("written_by", sa.Unicode(6), nullable=False),
        sa.Column("model", sa.Unicode(60), nullable=True),
        sa.Column("facts_json", sa.UnicodeText(), nullable=False),
        sa.Column("findings_json", sa.UnicodeText(), nullable=False),
        sa.Column("generated_by", sa.Unicode(200), nullable=False),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "written_by IN ('claude', 'rules')", name="ck_monthly_report_written_by"
        ),
        sa.UniqueConstraint("month", name="uq_monthly_report_month"),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("monthly_report", schema="core")
