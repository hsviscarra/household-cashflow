"""App categories on purchase items (ADR-050).

core.invoice_line.category_id and core.product_rule.category_id (a product's category, applied to
every line with it); product_rule.product_group becomes optional (a rule can hold just a category).

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("invoice_line", "product_rule"):
        op.add_column(table, sa.Column("category_id", sa.Integer()), schema="core")
        op.create_foreign_key(
            f"fk_{table}_category",
            table,
            "category",
            ["category_id"],
            ["category_id"],
            source_schema="core",
            referent_schema="core",
        )
    op.alter_column(
        "product_rule",
        "product_group",
        existing_type=sa.Unicode(40),
        nullable=True,
        schema="core",
    )


def downgrade() -> None:
    op.execute("DELETE FROM [core].[product_rule] WHERE [product_group] IS NULL")
    op.alter_column(
        "product_rule",
        "product_group",
        existing_type=sa.Unicode(40),
        nullable=False,
        schema="core",
    )
    for table in ("product_rule", "invoice_line"):
        op.drop_constraint(f"fk_{table}_category", table, schema="core", type_="foreignkey")
        op.drop_column(table, "category_id", schema="core")
