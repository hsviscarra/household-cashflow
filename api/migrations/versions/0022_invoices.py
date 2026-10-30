"""Electronic invoices (F21, ADR-021): core.invoice (an SRI factura and the line it was paid
with), core.invoice_line (its products, each with a product group) and core.product_rule (a
product's group, confirmed once).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)
QTY = sa.Numeric(19, 6)
# Frozen here: a later migration that adds a group changes the constraint itself.
PRODUCT_GROUPS = (
    "Meat & Fish",
    "Dairy & Eggs",
    "Fruit & Vegetables",
    "Bakery",
    "Pantry",
    "Snacks & Sweets",
    "Drinks",
    "Alcohol",
    "Frozen & Ready Meals",
    "Baby",
    "Household & Cleaning",
    "Personal Care",
    "Health & Pharmacy",
    "Pets",
    "Services",
    "Car",
    "Other",
)
GROUP_SOURCES = ("rule", "keyword", "claude", "confirmed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "invoice",
        sa.Column("invoice_id", sa.Integer(), primary_key=True),
        sa.Column("access_key", sa.Unicode(49), nullable=False),
        sa.Column("issuer_ruc", sa.Unicode(13), nullable=False),
        sa.Column("issuer_name", sa.Unicode(300), nullable=False),
        sa.Column("number", sa.Unicode(20), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("subtotal", MONEY, nullable=False),
        sa.Column("tax", MONEY, nullable=False),
        sa.Column("total", MONEY, nullable=False),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.transaction.transaction_id",
                name="fk_invoice_transaction_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("received_by", sa.Unicode(320), nullable=False),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("access_key", name="uq_invoice_access_key"),
        schema="core",
    )
    op.create_index("ix_invoice_issue_date", "invoice", ["issue_date"], schema="core")
    op.create_index("ix_invoice_transaction_id", "invoice", ["transaction_id"], schema="core")

    op.create_table(
        "invoice_line",
        sa.Column("line_id", sa.Integer(), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.invoice.invoice_id", name="fk_invoice_line_invoice_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("code", sa.Unicode(60), nullable=True),
        sa.Column("description", sa.Unicode(300), nullable=False),
        sa.Column("product_key", sa.Unicode(300), nullable=False),
        sa.Column("quantity", QTY, nullable=False),
        sa.Column("unit_price", QTY, nullable=False),
        sa.Column("discount", MONEY, nullable=False),
        sa.Column("subtotal", MONEY, nullable=False),
        sa.Column("tax", MONEY, nullable=False),
        sa.Column("total", MONEY, nullable=False),
        sa.Column("product_group", sa.Unicode(40), nullable=True),
        sa.Column("group_source", sa.Unicode(10), nullable=True),
        sa.CheckConstraint(
            f"product_group IS NULL OR {_in('product_group', PRODUCT_GROUPS)}",
            name="ck_invoice_line_group",
        ),
        sa.CheckConstraint(
            f"group_source IS NULL OR {_in('group_source', GROUP_SOURCES)}",
            name="ck_invoice_line_source",
        ),
        schema="core",
    )
    op.create_index("ix_invoice_line_invoice_id", "invoice_line", ["invoice_id"], schema="core")
    op.create_index("ix_invoice_line_product_key", "invoice_line", ["product_key"], schema="core")

    op.create_table(
        "product_rule",
        sa.Column("rule_id", sa.Integer(), primary_key=True),
        sa.Column("product_key", sa.Unicode(300), nullable=False),
        sa.Column("product_group", sa.Unicode(40), nullable=False),
        sa.Column("created_by", sa.Unicode(320), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("product_key", name="uq_product_rule_product_key"),
        sa.CheckConstraint(_in("product_group", PRODUCT_GROUPS), name="ck_product_rule_group"),
        schema="core",
    )
    # Claude's read-only login reads purchases by product group (ADR-017).
    op.execute("GRANT SELECT ON [core].[invoice] TO [mart_reader];")
    op.execute("GRANT SELECT ON [core].[invoice_line] TO [mart_reader];")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON [core].[invoice_line] FROM [mart_reader];")
    op.execute("REVOKE SELECT ON [core].[invoice] FROM [mart_reader];")
    op.drop_table("product_rule", schema="core")
    op.drop_index("ix_invoice_line_product_key", table_name="invoice_line", schema="core")
    op.drop_index("ix_invoice_line_invoice_id", table_name="invoice_line", schema="core")
    op.drop_table("invoice_line", schema="core")
    op.drop_index("ix_invoice_transaction_id", table_name="invoice", schema="core")
    op.drop_index("ix_invoice_issue_date", table_name="invoice", schema="core")
    op.drop_table("invoice", schema="core")
