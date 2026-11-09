"""Debt payment categories (ADR-054).

A category kind 'debt': its lines are debt payments (type debt_payment), not savings or spending.
Hernan: "house payments is debt payments" - the new house (a purchase being paid off), the BIESS
mortgage and Lauren's US education loans. Statement lines only got debt_payment from the workbook
before, so loan payments loaded from statements counted as savings.

Upgrade marks as 'debt' Savings & Debt / Loan Payments, Housing / Mortgage BIESS and every
category a loan or a purchase in progress is paid through, then turns their savings or spending
lines and recurring items into debt payments. Downgrade puts those categories back to savings
(Mortgage BIESS back to spending) and their lines, except the workbook's (debt payments already),
back to savings.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "kind IN ('income', 'expense', 'savings', 'transfer')"
NEW = "kind IN ('income', 'expense', 'savings', 'transfer', 'debt')"
DEBT = "SELECT [category_id] FROM [core].[category] WHERE [kind] = 'debt'"


def upgrade() -> None:
    op.drop_constraint("ck_category_kind", "category", schema="core", type_="check")
    op.create_check_constraint("ck_category_kind", "category", NEW, schema="core")
    op.execute(
        """
        UPDATE [core].[category] SET [kind] = 'debt'
        WHERE [category_id] IN (
            SELECT [c].[category_id]
            FROM [core].[category] AS [c]
            INNER JOIN [core].[category] AS [p] ON [p].[category_id] = [c].[parent_id]
            WHERE ([c].[name] = N'Loan Payments' AND [p].[name] = N'Savings & Debt')
                OR ([c].[name] = N'Mortgage BIESS' AND [p].[name] = N'Housing')
        )
        OR [category_id] IN (
            SELECT [h].[category_id]
            FROM [core].[holding] AS [h]
            WHERE [h].[holding_class] IN ('loan', 'purchase') AND [h].[category_id] IS NOT NULL
        )
        """
    )
    op.execute(
        f"""
        UPDATE [core].[transaction] SET [type] = 'debt_payment'
        WHERE [category_id] IN ({DEBT}) AND [type] IN ('savings', 'expense')
        """
    )
    op.execute(
        f"""
        UPDATE [core].[recurring_template] SET [type] = 'debt_payment'
        WHERE [category_id] IN ({DEBT}) AND [type] IN ('savings', 'expense')
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE [core].[transaction] SET [type] = 'savings'
        WHERE [category_id] IN ({DEBT}) AND [type] = 'debt_payment'
            AND [source] <> 'excel_history'
        """
    )
    op.execute(
        f"""
        UPDATE [core].[recurring_template] SET [type] = 'savings'
        WHERE [category_id] IN ({DEBT}) AND [type] = 'debt_payment'
        """
    )
    op.execute(
        """
        UPDATE [core].[category] SET [kind] = 'expense'
        WHERE [kind] = 'debt' AND [name] = N'Mortgage BIESS'
        """
    )
    op.execute("UPDATE [core].[category] SET [kind] = 'savings' WHERE [kind] = 'debt'")
    op.drop_constraint("ck_category_kind", "category", schema="core", type_="check")
    op.create_check_constraint("ck_category_kind", "category", OLD, schema="core")
