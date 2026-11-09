"""Notas de crédito and débito in the IVA return (ADR-064).

core.tax_note holds credit and debit notes the household issued (they change its sales) or
received (they change its purchases).

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)


def upgrade() -> None:
    op.create_table(
        "tax_note",
        sa.Column("tax_note_id", sa.Integer(), primary_key=True),
        sa.Column("access_key", sa.Unicode(49), nullable=False),
        sa.Column("kind", sa.Unicode(10), nullable=False),
        sa.Column("direction", sa.Unicode(10), nullable=False),
        sa.Column("person", sa.Unicode(20), nullable=False),
        sa.Column("issuer_ruc", sa.Unicode(13), nullable=False),
        sa.Column("issuer_name", sa.Unicode(300), nullable=False),
        sa.Column("counterpart_name", sa.Unicode(300), nullable=False),
        sa.Column("number", sa.Unicode(20), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("modified_number", sa.Unicode(20)),
        sa.Column("reason", sa.Unicode(300)),
        sa.Column("base_taxed", MONEY, nullable=False),
        sa.Column("base_zero", MONEY, nullable=False),
        sa.Column("tax", MONEY, nullable=False),
        sa.Column("total", MONEY, nullable=False),
        sa.Column("received_by", sa.Unicode(320), nullable=False),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("access_key", name="uq_tax_note_access_key"),
        sa.CheckConstraint("kind IN ('credit', 'debit')", name="ck_tax_note_kind"),
        sa.CheckConstraint("direction IN ('issued', 'received')", name="ck_tax_note_direction"),
        schema="core",
    )
    op.create_index("ix_tax_note_issue_date", "tax_note", ["issue_date"], schema="core")


def downgrade() -> None:
    op.drop_index("ix_tax_note_issue_date", "tax_note", schema="core")
    op.drop_table("tax_note", schema="core")
