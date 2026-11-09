"""Nelnet on Net worth, and old workbook rows that duplicate real accounts paused (ADR-057).

Hernan, Nov 9 2026: add Lauren's Nelnet loan (on hold, no payments) as a debt, and stop counting
the workbook's last values for Stock Market, Produbanco, Mastercard HV and Diners, which are the
same money as Interactive Brokers and the accounts read from statements.

Upgrade adds the loan Nelnet with its last workbook balance, 68,190.32 (Cash Flow 2025, DEUDAS),
dated Dec 31 2025, and pauses the four workbook items (their history stays). Downgrade removes
Nelnet and makes the four active again.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DUPLICATES = ("Stock Market", "Produbanco", "Mastercard HV", "Diners")
NAME = "Nelnet"


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- Nelnet and the paused workbook items are set only in online mode")
        return
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE [h] SET [h].[is_active] = 0
            FROM [core].[holding] AS [h]
            WHERE [h].[name] IN (:a, :b, :c, :d)
              AND NOT EXISTS (
                SELECT 1 FROM [core].[balance_snapshot] AS [s]
                WHERE [s].[holding_id] = [h].[holding_id] AND [s].[source] <> N'excel'
              )
            """
        ),
        dict(zip("abcd", DUPLICATES, strict=True)),
    )
    if conn.execute(
        sa.text("SELECT 1 FROM [core].[holding] WHERE [name] = :n"), {"n": NAME}
    ).first():
        return
    conn.execute(
        sa.text(
            """
            INSERT INTO [core].[holding]
                ([name], [side], [holding_class], [is_active], [sort_order], [notes])
            SELECT :n, N'liability', N'loan', 1, COALESCE(MAX([sort_order]), 0) + 1,
                N'Lauren''s US education loan, on hold (no payments). Last balance from the '
                + N'Cash Flow workbook.'
            FROM [core].[holding]
            """
        ),
        {"n": NAME},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO [core].[balance_snapshot]
                ([as_of], [name], [kind], [amount], [source], [notes], [holding_id])
            SELECT '2025-12-31', [name], N'liability', 68190.32, N'manual',
                N'Cash Flow 2025, DEUDAS', [holding_id]
            FROM [core].[holding] WHERE [name] = :n
            """
        ),
        {"n": NAME},
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM [core].[balance_snapshot] WHERE [holding_id] IN (
            SELECT [holding_id] FROM [core].[holding]
            WHERE [name] = N'{NAME}' AND [holding_class] = N'loan'
        )
        """
    )
    op.execute(
        f"DELETE FROM [core].[holding] WHERE [name] = N'{NAME}' AND [holding_class] = N'loan'"
    )
    names = ", ".join(f"N'{n}'" for n in DUPLICATES)
    op.execute(f"UPDATE [core].[holding] SET [is_active] = 1 WHERE [name] IN ({names})")
