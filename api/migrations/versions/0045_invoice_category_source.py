"""A line's category can come from its invoice's products (ADR-066).

core.transaction.category_source allows 'invoice'.

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = ("rule", "section", "manual", "suggestion", "excel", "split", "match", "note", "person")


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
    _sources((*BEFORE, "invoice"))


def downgrade() -> None:
    op.execute(
        "UPDATE [core].[transaction] SET [category_source] = N'rule' "
        "WHERE [category_source] = N'invoice'"
    )
    _sources(BEFORE)
