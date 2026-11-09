"""Monthly IVA return (ADR-062): issued invoices, withholdings received, issuer rules.

core.sale_invoice holds the invoices the household issued, core.withholding the comprobantes de
retención clients issued to it, and core.tax_issuer_rule how a received invoice's issuer counts
(business purchase, personal expense or neither).

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)


def upgrade() -> None:
    op.create_table(
        "sale_invoice",
        sa.Column("sale_invoice_id", sa.Integer(), primary_key=True),
        sa.Column("access_key", sa.Unicode(49), nullable=False),
        sa.Column("person", sa.Unicode(20), nullable=False),
        sa.Column("number", sa.Unicode(20), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("buyer_name", sa.Unicode(300), nullable=False),
        sa.Column("base_taxed", MONEY, nullable=False),
        sa.Column("base_zero", MONEY, nullable=False),
        sa.Column("tax", MONEY, nullable=False),
        sa.Column("total", MONEY, nullable=False),
        sa.Column("received_by", sa.Unicode(320), nullable=False),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("access_key", name="uq_sale_invoice_access_key"),
        schema="core",
    )
    op.create_index("ix_sale_invoice_issue_date", "sale_invoice", ["issue_date"], schema="core")
    op.create_table(
        "withholding",
        sa.Column("withholding_id", sa.Integer(), primary_key=True),
        sa.Column("access_key", sa.Unicode(49), nullable=False),
        sa.Column("person", sa.Unicode(20), nullable=False),
        sa.Column("issuer_ruc", sa.Unicode(13), nullable=False),
        sa.Column("issuer_name", sa.Unicode(300), nullable=False),
        sa.Column("number", sa.Unicode(20), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("invoice_number", sa.Unicode(20)),
        sa.Column("income_tax", MONEY, nullable=False),
        sa.Column("iva", MONEY, nullable=False),
        sa.Column("received_by", sa.Unicode(320), nullable=False),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("access_key", name="uq_withholding_access_key"),
        schema="core",
    )
    op.create_index("ix_withholding_period", "withholding", ["period"], schema="core")
    op.create_table(
        "tax_issuer_rule",
        sa.Column("tax_issuer_rule_id", sa.Integer(), primary_key=True),
        sa.Column("issuer_ruc", sa.Unicode(13), nullable=False),
        sa.Column("iva_use", sa.Unicode(10), nullable=False),
        sa.Column("created_by", sa.Unicode(320), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("issuer_ruc", name="uq_tax_issuer_rule_issuer_ruc"),
        sa.CheckConstraint(
            "iva_use IN ('business', 'personal', 'none')", name="ck_tax_issuer_rule_iva_use"
        ),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("tax_issuer_rule", schema="core")
    op.drop_index("ix_withholding_period", "withholding", schema="core")
    op.drop_table("withholding", schema="core")
    op.drop_index("ix_sale_invoice_issue_date", "sale_invoice", schema="core")
    op.drop_table("sale_invoice", schema="core")
