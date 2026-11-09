"""Transfers / Exchange through people (ADR-055).

Money moves between the US and Ecuador by paying someone with accounts in both countries: a Zelle
payment from Bank of America, and that person deposits the same amount in an Ecuador account (or
the other way round). Neither side is income or spending. This adds the category; matching pairs
the two sides.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.seeds import load_v9

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _category() -> sa.Table:
    return sa.Table(
        "category",
        sa.MetaData(),
        sa.Column("category_id", sa.Integer, primary_key=True),
        sa.Column("parent_id", sa.Integer),
        sa.Column("name", sa.Unicode(100)),
        sa.Column("kind", sa.Unicode(10)),
        sa.Column("color", sa.Unicode(7)),
        sa.Column("is_fixed", sa.Boolean),
        sa.Column("sort_order", sa.Integer),
        sa.Column("description", sa.Unicode(400)),
        schema="core",
    )


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- seed v9 (Exchange through people) is loaded only in online mode")
        return
    load_v9(op.get_bind(), _category())


def downgrade() -> None:
    op.execute(
        """
        UPDATE [core].[transaction] SET [category_id] = NULL, [category_source] = NULL
        WHERE [category_id] IN (
            SELECT [c].[category_id] FROM [core].[category] AS [c]
            INNER JOIN [core].[category] AS [p] ON [p].[category_id] = [c].[parent_id]
            WHERE [c].[name] = N'Exchange through people' AND [p].[name] = N'Transfers'
        )
        """
    )
    op.execute(
        """
        DELETE [c] FROM [core].[category] AS [c]
        INNER JOIN [core].[category] AS [p] ON [p].[category_id] = [c].[parent_id]
        WHERE [c].[name] = N'Exchange through people' AND [p].[name] = N'Transfers'
        """
    )
