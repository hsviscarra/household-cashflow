"""Cost of debt (F14, ADR-011): mart.v_debt_cost, interest and fees per account and month.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-27
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A frozen copy: the head file changed in 0019 (statements from a chosen month).
VIEW = Path(__file__).resolve().parent.parent / "views" / "0018" / "mart.v_debt_cost.sql"


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS [mart].[v_debt_cost];")
    op.execute(VIEW.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS [mart].[v_debt_cost];")
