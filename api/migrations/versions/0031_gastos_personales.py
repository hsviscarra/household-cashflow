"""Gastos personales (ADR-036): whose invoice it is, its SRI category, issuer rules and each
person's cargas familiares per year.

core.invoice.person: Hernan or Lauren (from the buyer's ID matched at reading time against the
  INVOICE_BUYERS setting, or chosen by a person); the ID itself is never stored.
core.invoice.gp_category: a person's choice of SRI category, or 'none' = not deductible; empty =
  guessed from an issuer rule, the paying line's category or the products.
core.gp_issuer_rule: one SRI category per issuer RUC, saved from a person's choice.
core.gp_profile: cargas familiares and the catastrophic-illness case, per person and year.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = "('vivienda', 'educacion', 'salud', 'alimentacion', 'vestimenta', 'turismo')"


def upgrade() -> None:
    op.add_column("invoice", sa.Column("person", sa.Unicode(20)), schema="core")
    op.add_column("invoice", sa.Column("gp_category", sa.Unicode(20)), schema="core")
    op.create_check_constraint(
        "ck_invoice_gp_category",
        "invoice",
        f"gp_category IS NULL OR gp_category = 'none' OR gp_category IN {CATEGORIES}",
        schema="core",
    )
    op.create_table(
        "gp_issuer_rule",
        sa.Column("gp_issuer_rule_id", sa.Integer(), primary_key=True),
        sa.Column("issuer_ruc", sa.Unicode(13), nullable=False, unique=True),
        sa.Column("gp_category", sa.Unicode(20), nullable=False),
        sa.Column("created_by", sa.Unicode(320), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            f"gp_category = 'none' OR gp_category IN {CATEGORIES}",
            name="ck_gp_issuer_rule_category",
        ),
        schema="core",
    )
    op.create_table(
        "gp_profile",
        sa.Column("person", sa.Unicode(20), primary_key=True),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("cargas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("catastrophic", sa.Boolean(), server_default="0", nullable=False),
        sa.CheckConstraint("cargas >= 0 AND cargas <= 20", name="ck_gp_profile_cargas"),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("gp_profile", schema="core")
    op.drop_table("gp_issuer_rule", schema="core")
    op.drop_constraint("ck_invoice_gp_category", "invoice", schema="core", type_="check")
    op.drop_column("invoice", "gp_category", schema="core")
    op.drop_column("invoice", "person", schema="core")
