"""Bank sync through SimpleFIN (ADR-044).

core.account.sync_id: the SimpleFIN account that feeds it (an opaque id), unique when set.
core.transaction.source gains 'bank_sync': lines from the daily sync, kept as 'pending' until
their statement arrives and takes their place.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "source IN ('statement', 'manual', 'excel_history')"
NEW = "source IN ('statement', 'manual', 'excel_history', 'bank_sync')"


def upgrade() -> None:
    op.add_column("account", sa.Column("sync_id", sa.Unicode(100)), schema="core")
    op.create_index(
        "ux_account_sync_id",
        "account",
        ["sync_id"],
        unique=True,
        schema="core",
        mssql_where=sa.text("sync_id IS NOT NULL"),
        sqlite_where=sa.text("sync_id IS NOT NULL"),
    )
    op.drop_constraint("ck_transaction_source", "transaction", schema="core", type_="check")
    op.create_check_constraint("ck_transaction_source", "transaction", NEW, schema="core")


def downgrade() -> None:
    op.execute("DELETE FROM [core].[transaction] WHERE [source] = 'bank_sync'")
    op.drop_constraint("ck_transaction_source", "transaction", schema="core", type_="check")
    op.create_check_constraint("ck_transaction_source", "transaction", OLD, schema="core")
    op.drop_index("ux_account_sync_id", "account", schema="core")
    op.drop_column("account", "sync_id", schema="core")
