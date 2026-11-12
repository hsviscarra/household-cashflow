"""A salary counts in the month it pays for (ADR-084).

Hernan, Nov 12 2026: he is paid around the 20th and Lauren on the last day of the month, both for
the month that follows, so November showed no income until the 20th. A salary (money in, category
under the income group "Salary") received on the 15th or later now counts in the next month; one
received before the 15th counts in its own month, which also undoes ADR-070's move of a payroll
paid on the 1st or 2nd to the month before.

Upgrade moves the salaries already loaded from a bank (statements and the bank sync; the
workbook's months are left alone) and points each one's recurring link at the same item's entry
in its new month, or clears it when that month has none. Every change is logged in
audit.change_log; downgrade puts every logged value back.

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import context, op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASON = "migration 0051"

# Step 1: the salaries whose month changes, with the month each one pays for.
MOVES = """
    SELECT [t].[transaction_id], [t].[cash_month] AS [old_month],
        CASE WHEN DAY([t].[txn_date]) >= 15
            THEN DATEADD(MONTH, 1, DATEFROMPARTS(YEAR([t].[txn_date]), MONTH([t].[txn_date]), 1))
            ELSE DATEFROMPARTS(YEAR([t].[txn_date]), MONTH([t].[txn_date]), 1)
        END AS [new_month],
        [t].[recurring_entry_id] AS [old_entry]
    INTO #moves
    FROM [core].[transaction] AS [t]
    INNER JOIN [core].[category] AS [c] ON [c].[category_id] = [t].[category_id]
    INNER JOIN [core].[category] AS [g] ON [g].[category_id] = [c].[parent_id]
    WHERE [t].[source] IN ('statement', 'bank_sync')
      AND [t].[amount] > 0
      AND [g].[name] = N'Salary'
      AND [g].[parent_id] IS NULL;
"""
KEEP_CHANGED = "DELETE FROM #moves WHERE [new_month] = [old_month];"
# Step 2: the same recurring item's entry in the new month, when there is one.
ENTRIES = """
    SELECT [m].[transaction_id], [m].[old_entry], [e2].[entry_id] AS [new_entry]
    INTO #links
    FROM #moves AS [m]
    INNER JOIN [core].[recurring_entry] AS [e1] ON [e1].[entry_id] = [m].[old_entry]
    LEFT JOIN [core].[recurring_entry] AS [e2]
        ON [e2].[template_id] = [e1].[template_id] AND [e2].[month] = [m].[new_month];
"""
LOG_MONTH = f"""
    INSERT INTO [audit].[change_log]
        ([table_name], [row_id], [column_name], [old_value], [new_value], [reason], [changed_by])
    SELECT N'core.transaction', [m].[transaction_id], N'cash_month',
        CONVERT(NVARCHAR(10), [m].[old_month], 23), CONVERT(NVARCHAR(10), [m].[new_month], 23),
        N'{REASON}', N'system'
    FROM #moves AS [m];
"""
LOG_ENTRY = f"""
    INSERT INTO [audit].[change_log]
        ([table_name], [row_id], [column_name], [old_value], [new_value], [reason], [changed_by])
    SELECT N'core.transaction', [l].[transaction_id], N'recurring_entry_id',
        CAST([l].[old_entry] AS NVARCHAR(400)), CAST([l].[new_entry] AS NVARCHAR(400)),
        N'{REASON}', N'system'
    FROM #links AS [l];
"""
MOVE = """
    UPDATE [t] SET [t].[cash_month] = [m].[new_month]
    FROM [core].[transaction] AS [t]
    INNER JOIN #moves AS [m] ON [m].[transaction_id] = [t].[transaction_id];
"""
RELINK = """
    UPDATE [t] SET [t].[recurring_entry_id] = [l].[new_entry]
    FROM [core].[transaction] AS [t]
    INNER JOIN #links AS [l] ON [l].[transaction_id] = [t].[transaction_id];
"""
RESTORE = """
    UPDATE [t] SET [t].[{column}] = {cast}
    FROM [core].[transaction] AS [t]
    INNER JOIN [audit].[change_log] AS [l]
        ON [l].[row_id] = [t].[transaction_id]
       AND [l].[table_name] = N'core.transaction'
       AND [l].[column_name] = N'{column}'
       AND [l].[reason] = N'{reason}';
"""


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- 0051 changes data only in online mode")
        return
    # One batch on one connection: the #temp tables live for all of it.
    batch = "SET NOCOUNT ON;\n" + "\n".join(
        (MOVES, KEEP_CHANGED, ENTRIES, LOG_MONTH, LOG_ENTRY, MOVE, RELINK)
    )
    # NOCOUNT goes back off: Alembic checks the row count of its own version update.
    op.get_bind().exec_driver_sql(
        batch + "\nDROP TABLE #links;\nDROP TABLE #moves;\nSET NOCOUNT OFF;"
    )


def downgrade() -> None:
    for column, cast in (
        ("cash_month", "TRY_CAST([l].[old_value] AS DATE)"),
        ("recurring_entry_id", "TRY_CAST([l].[old_value] AS INT)"),
    ):
        op.execute(RESTORE.format(column=column, cast=cast, reason=REASON))
    op.execute(
        f"DELETE FROM [audit].[change_log] WHERE [reason] = N'{REASON}' "
        "AND [table_name] = N'core.transaction';"
    )
