"""Account closing date: core.account.closed_on. A closed or suspended account (Hernan's Pichincha
card, suspended in September 2026) stops being expected on the month-status page after that day;
its earlier statements still load.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("account", sa.Column("closed_on", sa.Date(), nullable=True), schema="core")


def downgrade() -> None:
    op.drop_column("account", "closed_on", schema="core")
