"""Account opening date: core.account.opened_on (ADR-071). No statements are expected before it,
so a card opened in October doesn't show August and September as missing.

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("account", sa.Column("opened_on", sa.Date(), nullable=True), schema="core")


def downgrade() -> None:
    op.drop_column("account", "opened_on", schema="core")
