"""Type of product and brand on purchase items (ADR-061).

core.invoice_line and core.product_rule get product_type (e.g. Cheese, Chicken, Diapers) and
brand (e.g. Kiosko, Mr. Pollo), so groceries can be read by aisle, type and brand.
invoice_line.label_source says who set them: claude, or confirmed by a person (from the
product's rule).

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("invoice_line", "product_rule"):
        op.add_column(table, sa.Column("product_type", sa.Unicode(60)), schema="core")
        op.add_column(table, sa.Column("brand", sa.Unicode(60)), schema="core")
    op.add_column("invoice_line", sa.Column("label_source", sa.Unicode(10)), schema="core")
    op.create_check_constraint(
        "ck_invoice_line_label_source",
        "invoice_line",
        "label_source IS NULL OR label_source IN ('claude', 'confirmed')",
        schema="core",
    )


def downgrade() -> None:
    op.drop_constraint("ck_invoice_line_label_source", "invoice_line", schema="core", type_="check")
    op.drop_column("invoice_line", "label_source", schema="core")
    for table in ("product_rule", "invoice_line"):
        op.drop_column(table, "brand", schema="core")
        op.drop_column(table, "product_type", schema="core")
