"""Spending analytics (F13, ADR-010): mart.v_spending_line, one row per line that counts as
spending, with its group, category, person, country, fixed flag and merchant.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-27
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW = Path(__file__).resolve().parent.parent / "views" / "mart.v_spending_line.sql"


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS [mart].[v_spending_line];")
    op.execute(VIEW.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS [mart].[v_spending_line];")
