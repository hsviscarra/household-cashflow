"""The app category chosen for an SRI invoice (ADR-045).

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("invoice", sa.Column("category_id", sa.Integer()), schema="core")
    op.create_foreign_key(
        "fk_invoice_category",
        "invoice",
        "category",
        ["category_id"],
        ["category_id"],
        source_schema="core",
        referent_schema="core",
    )


def downgrade() -> None:
    op.drop_constraint("fk_invoice_category", "invoice", schema="core", type_="foreignkey")
    op.drop_column("invoice", "category_id", schema="core")
