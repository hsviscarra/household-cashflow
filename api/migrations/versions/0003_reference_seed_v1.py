"""Seed v1: accounts, category tree and first merchant rules (F1).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import context, op

from app.models import Account, Category, MerchantRule
from app.seeds import load_v1

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if context.is_offline_mode():
        # Seeding needs generated ids, so it only runs against a live database.
        op.execute("-- seed v1 is loaded only in online mode")
        return
    load_v1(op.get_bind(), Account.__table__, Category.__table__, MerchantRule.__table__)


def downgrade() -> None:
    op.execute("DELETE FROM core.merchant_rule")
    # Children first, then groups, because of the self-referencing foreign key.
    op.execute("DELETE FROM core.category WHERE parent_id IS NOT NULL")
    op.execute("DELETE FROM core.category")
    op.execute("DELETE FROM core.account")
