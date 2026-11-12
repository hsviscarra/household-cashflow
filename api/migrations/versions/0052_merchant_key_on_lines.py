"""The merchant key on every line (ADR-086): `core.transaction.merchant_key`, what groups the
lines of one merchant (the description without reference numbers, store numbers and confirmation
codes). It was recomputed for every line each time To do, rule suggestions or subscriptions were
built; stored and indexed, those become GROUP BY queries. Filled here for the lines already
loaded, with the same function the app uses (`app.services.rules.key`).

Revision ID: 0052
Revises: 0051
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.services.rules import MAX_KEY, key

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_transaction_merchant_key"
BATCH = 500  # lines per UPDATE round trip


def _fill() -> None:
    """Give the lines already loaded their key; new lines get it from the app as they're saved."""
    if context.is_offline_mode():
        op.execute("-- 0052 fills merchant_key only in online mode")
        return
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT [t].[transaction_id], [t].[description_raw] FROM [core].[transaction] AS [t]"
        )
    ).all()
    fill = sa.text(
        "UPDATE [core].[transaction] SET [merchant_key] = :k WHERE [transaction_id] = :i"
    )
    for start in range(0, len(rows), BATCH):
        bind.execute(
            fill, [{"i": i, "k": key(text or "")} for i, text in rows[start : start + BATCH]]
        )


def upgrade() -> None:
    op.add_column(
        "transaction",
        sa.Column("merchant_key", sa.Unicode(MAX_KEY), nullable=True),
        schema="core",
    )
    _fill()
    op.create_index(INDEX, "transaction", ["merchant_key"], schema="core")


def downgrade() -> None:
    op.drop_index(INDEX, table_name="transaction", schema="core")
    op.drop_column("transaction", "merchant_key", schema="core")
