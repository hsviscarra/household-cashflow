"""Lauren's Diners card is kept for Juliana's education (ADR-074): Hernan, Nov 11 2026 — school,
bus, food and insurance, billed by Colegio Einstein and Skole. Lines that don't look like those
are flagged on To do for a person to check. Stored as core.app_setting
'card-purpose:<account_id>'; no schema change.

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-11
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PURPOSE = {"for": "Juliana", "usual": ["EINSTEIN", "SKOLE", "DEUDA ASEGURADA"]}


def upgrade() -> None:
    if context.is_offline_mode():
        return
    conn = op.get_bind()
    aid = conn.execute(
        sa.text("SELECT [account_id] FROM [core].[account] WHERE [name] = N'Diners Club Lauren'")
    ).scalar()
    if aid is None:
        return
    key = f"card-purpose:{aid}"
    exists = conn.execute(
        sa.text("SELECT 1 FROM [core].[app_setting] WHERE [setting_key] = :k"), {"k": key}
    ).scalar()
    if exists:
        return
    conn.execute(
        sa.text(
            "INSERT INTO [core].[app_setting] ([setting_key], [setting_value], [updated_by]) "
            "VALUES (:k, :v, N'migration 0049')"
        ),
        {"k": key, "v": json.dumps(PURPOSE)},
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM [core].[app_setting] WHERE [setting_key] LIKE N'card-purpose:%' "
        "AND [updated_by] = N'migration 0049'"
    )
