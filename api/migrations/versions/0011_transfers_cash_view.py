"""Transfers and two views (F10): transfer_group_id links both legs of a transfer between own
accounts; 'match' as a category source; mart.v_monthly_cash (ADR-007).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-26
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A frozen copy: the head file changed in 0019 (statements from a chosen month).
VIEW = Path(__file__).resolve().parent.parent / "views" / "0018" / "mart.v_monthly_cash.sql"
SOURCES = ("rule", "section", "manual", "suggestion", "excel", "split")


def _sources(values: tuple[str, ...]) -> None:
    op.drop_constraint(
        "ck_transaction_category_source", "transaction", schema="core", type_="check"
    )
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(
        "ck_transaction_category_source",
        "transaction",
        f"category_source IN ({listed})",
        schema="core",
    )


def upgrade() -> None:
    op.add_column(
        "transaction", sa.Column("transfer_group_id", sa.Integer(), nullable=True), schema="core"
    )
    op.create_index(
        "ix_transaction_transfer_group_id", "transaction", ["transfer_group_id"], schema="core"
    )
    _sources((*SOURCES, "match"))
    op.execute("DROP VIEW IF EXISTS [mart].[v_monthly_cash];")
    op.execute(VIEW.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS [mart].[v_monthly_cash];")
    # Matched legs keep their transfer category; only the link and its label go.
    op.execute(
        "UPDATE [core].[transaction] SET [category_source] = 'rule' "
        "WHERE [category_source] = 'match';"
    )
    _sources(SOURCES)
    op.drop_index("ix_transaction_transfer_group_id", table_name="transaction", schema="core")
    op.drop_column("transaction", "transfer_group_id", schema="core")
