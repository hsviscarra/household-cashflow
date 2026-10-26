"""Views count a month from the Excel history or from statements, never both (F6, ADR-004).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEWS = ("mart.v_monthly_cashflow", "mart.v_category_month")
ROOT = Path(__file__).resolve().parent.parent / "views"


def _recreate(folder: Path) -> None:
    for view in VIEWS:
        schema, name = view.split(".")
        op.execute(f"DROP VIEW IF EXISTS [{schema}].[{name}];")
        op.execute((folder / f"{view}.sql").read_text(encoding="utf-8"))


def upgrade() -> None:
    _recreate(ROOT / "0008")  # frozen: the current definitions need later columns


def downgrade() -> None:
    _recreate(ROOT / "0004")
