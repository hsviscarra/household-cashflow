"""Statements from a chosen month (F19, ADR-018): core.app_setting holds "statements_from"; the
months the workbook counts are mart.v_excel_month (every workbook month before it), and the five
mart views use it, so from that month on statements count and the workbook is a reference only.
Without the setting nothing changes (the workbook wins every month it covers, ADR-004).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-28
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROOT = Path(__file__).resolve().parent.parent / "views"
# Dependents first when dropping; v_excel_month must exist before the others are created.
VIEWS = (
    "mart.v_monthly_cashflow",
    "mart.v_monthly_cash",
    "mart.v_category_month",
    "mart.v_spending_line",
    "mart.v_debt_cost",
)


def _recreate(folder: Path) -> None:
    for view in VIEWS:
        schema, name = view.split(".")
        op.execute(f"DROP VIEW IF EXISTS [{schema}].[{name}];")
        op.execute((folder / f"{view}.sql").read_text(encoding="utf-8"))


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("setting_key", sa.Unicode(50), primary_key=True),
        sa.Column("setting_value", sa.Unicode(200), nullable=False),
        sa.Column("updated_by", sa.Unicode(200), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="core",
    )
    op.execute((ROOT / "mart.v_excel_month.sql").read_text(encoding="utf-8"))
    _recreate(ROOT)


def downgrade() -> None:
    _recreate(ROOT / "0018")
    op.execute("DROP VIEW IF EXISTS [mart].[v_excel_month];")
    op.drop_table("app_setting", schema="core")
