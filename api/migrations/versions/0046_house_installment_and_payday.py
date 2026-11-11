"""The new house's installment by amount, and early salaries in their month (ADR-070).

Hernan, Nov 10 2026: the new house's monthly installment (3,075.36) and the 25,678.22 down payment
leave Lauren's Produbanco as "TRANSFERENCIA CTAS TERCEROS BCA ENL", which never names the trust,
so they were counted as transfers between own accounts and left out of the cash flow; and
Lauren's payroll ("ROL DE PAGOS") paid on the 1st belongs to the month before.

Upgrade adds a rule for that text at exactly 3,075.36 (Housing / New house), moves the loaded
installments and the down payment there as debt payments, and moves salaries paid on the 1st or
2nd to the month before. Each change is logged in audit.change_log; downgrade puts every logged
value back and removes the rule. A line a person categorized is left alone.

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.seeds import load_v11

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASON = "migration 0046"
CATEGORY = """
    SELECT [c].[category_id] FROM [core].[category] AS [c]
    INNER JOIN [core].[category] AS [p] ON [p].[category_id] = [c].[parent_id]
    WHERE [c].[name] = N'New house' AND [p].[name] = N'Housing'
"""
HOUSE = """
    FROM [core].[transaction] AS [t]
    WHERE [t].[source] IN ('statement', 'bank_sync')
      AND UPPER([t].[description_raw]) LIKE N'%CTAS TERCEROS%'
      AND [t].[amount] IN (-3075.36, -25678.22)
      AND ([t].[transfer_group_id] IS NULL OR [t].[transfer_group_id] = [t].[transaction_id])
      AND ISNULL([t].[category_source], N'') NOT IN (N'manual', N'split', N'person', N'note')
"""
PAYDAY = """
    FROM [core].[transaction] AS [t]
    WHERE [t].[source] IN ('statement', 'bank_sync')
      AND UPPER([t].[description_raw]) LIKE N'%ROL DE PAGOS%'
      AND [t].[amount] > 0
      AND DAY([t].[txn_date]) <= 2
      AND [t].[cash_month] = DATEFROMPARTS(YEAR([t].[txn_date]), MONTH([t].[txn_date]), 1)
"""


def _tables() -> tuple[sa.Table, sa.Table]:
    md = sa.MetaData()
    category = sa.Table(
        "category",
        md,
        sa.Column("category_id", sa.Integer, primary_key=True),
        sa.Column("parent_id", sa.Integer),
        sa.Column("name", sa.Unicode(100)),
        schema="core",
    )
    rule = sa.Table(
        "merchant_rule",
        md,
        sa.Column("rule_id", sa.Integer, primary_key=True),
        sa.Column("pattern", sa.Unicode(200)),
        sa.Column("match_type", sa.Unicode(12)),
        sa.Column("category_id", sa.Integer),
        sa.Column("priority", sa.Integer),
        sa.Column("amount_min", sa.Numeric(19, 4)),
        sa.Column("amount_max", sa.Numeric(19, 4)),
        schema="core",
    )
    return category, rule


def _log(conn: sa.Connection, lines: str, column: str, old: str, new: str, **p: object) -> None:
    changed = f"{old} IS NOT NULL" if new == "NULL" else f"({old} IS NULL OR {old} <> {new})"
    conn.execute(
        sa.text(
            f"""
            INSERT INTO [audit].[change_log]
                ([table_name], [row_id], [column_name], [old_value], [new_value], [reason],
                 [changed_by])
            SELECT N'core.transaction', [t].[transaction_id], N'{column}',
                CAST({old} AS NVARCHAR(400)), CAST({new} AS NVARCHAR(400)), N'{REASON}', N'system'
            {lines}
              AND {changed}
            """
        ),
        p,
    )


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- 0046 changes data only in online mode")
        return
    conn = op.get_bind()
    category, rule = _tables()
    load_v11(conn, category, rule)
    cid = conn.execute(sa.text(CATEGORY)).scalar_one_or_none()
    if cid is not None:
        _log(conn, HOUSE, "category_id", "[t].[category_id]", ":cid", cid=cid)
        _log(conn, HOUSE, "type", "[t].[type]", "N'debt_payment'")
        _log(conn, HOUSE, "category_source", "[t].[category_source]", "N'rule'")
        _log(conn, HOUSE, "transfer_group_id", "[t].[transfer_group_id]", "NULL")
        conn.execute(
            sa.text(
                f"""
                UPDATE [t] SET [t].[category_id] = :cid, [t].[type] = N'debt_payment',
                    [t].[category_source] = N'rule', [t].[transfer_group_id] = NULL
                {HOUSE}
                """
            ),
            {"cid": cid},
        )
    _log(
        conn,
        PAYDAY,
        "cash_month",
        "CONVERT(NVARCHAR(10), [t].[cash_month], 23)",
        "CONVERT(NVARCHAR(10), DATEADD(MONTH, -1, [t].[cash_month]), 23)",
    )
    conn.execute(
        sa.text(f"UPDATE [t] SET [t].[cash_month] = DATEADD(MONTH, -1, [t].[cash_month]) {PAYDAY}")
    )


def downgrade() -> None:
    for column, cast in (
        ("category_id", "TRY_CAST([l].[old_value] AS INT)"),
        ("type", "[l].[old_value]"),
        ("category_source", "[l].[old_value]"),
        ("cash_month", "TRY_CAST([l].[old_value] AS DATE)"),
        ("transfer_group_id", "TRY_CAST([l].[old_value] AS INT)"),
    ):
        op.execute(
            f"""
            UPDATE [t] SET [t].[{column}] = {cast}
            FROM [core].[transaction] AS [t]
            INNER JOIN [audit].[change_log] AS [l]
                ON [l].[row_id] = [t].[transaction_id]
               AND [l].[table_name] = N'core.transaction'
               AND [l].[column_name] = N'{column}'
               AND [l].[reason] = N'{REASON}'
            """
        )
    op.execute(
        "DELETE FROM [core].[merchant_rule] "
        "WHERE [pattern] = N'TRANSFERENCIA CTAS TERCEROS' AND [amount_min] = 3075.36"
    )
