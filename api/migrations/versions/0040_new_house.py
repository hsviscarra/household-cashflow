"""The new house as a purchase in progress (ADR-056).

Hernan, Nov 9 2026: the new house's 30% down payment is a 2,000.00 reserva, a 25,678.22 entrada and
18 monthly installments of 3,075.36, all paid from Lauren's Produbanco account to the developer's
trust (Fideicomiso Inmobiliario Kalani); two installments are paid. The rest is financed at
delivery.

Upgrade adds Housing / New house (kind debt) and a rule sending the trust's lines there, moves the
lines already loaded to it as debt payments (each change in audit.change_log), and adds the
purchase on Net worth: down payment 83,034.70 (2,000 + 25,678.22 + 18 x 3,075.36), installment
3,075.36, and 33,829.94 paid so far on Nov 9 2026. Later lines in the category add to what's paid.
Downgrade removes the purchase, the rule and the category; the moved lines go back to having no
category.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.seeds import load_v10

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "New house"
CATEGORY = """
    SELECT [c].[category_id] FROM [core].[category] AS [c]
    INNER JOIN [core].[category] AS [p] ON [p].[category_id] = [c].[parent_id]
    WHERE [c].[name] = N'New house' AND [p].[name] = N'Housing'
"""
LINES = """
    FROM [core].[transaction] AS [t]
    WHERE [t].[source] IN ('statement', 'bank_sync')
      AND UPPER([t].[description_raw]) LIKE N'%KALANI%'
      AND [t].[transfer_group_id] IS NULL
"""


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


def _merchant_rule() -> sa.Table:
    return sa.Table(
        "merchant_rule",
        sa.MetaData(),
        sa.Column("rule_id", sa.Integer, primary_key=True),
        sa.Column("pattern", sa.Unicode(200)),
        sa.Column("match_type", sa.Unicode(12)),
        sa.Column("category_id", sa.Integer),
        sa.Column("priority", sa.Integer),
        schema="core",
    )


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- seed v10 and the new house purchase are loaded only in online mode")
        return
    conn = op.get_bind()
    load_v10(conn, _category(), _merchant_rule())
    cid = conn.execute(sa.text(CATEGORY)).scalar_one_or_none()
    if cid is None:
        return
    for column, old in (("category_id", "[t].[category_id]"), ("type", "[t].[type]")):
        new = ":cid" if column == "category_id" else "N'debt_payment'"
        conn.execute(
            sa.text(
                f"""
                INSERT INTO [audit].[change_log]
                    ([table_name], [row_id], [column_name], [old_value], [new_value], [reason],
                     [changed_by])
                SELECT N'core.transaction', [t].[transaction_id], N'{column}',
                    CAST({old} AS NVARCHAR(400)), CAST({new} AS NVARCHAR(400)),
                    N'New house payment (migration 0040)', N'system'
                {LINES}
                  AND ({old} IS NULL OR {old} <> {new})
                """
            ),
            {"cid": cid},
        )
    conn.execute(
        sa.text(
            f"""
            UPDATE [t] SET [t].[category_id] = :cid, [t].[type] = N'debt_payment',
                [t].[category_source] = N'rule', [t].[is_fixed] = 1
            {LINES}
            """
        ),
        {"cid": cid},
    )
    if conn.execute(
        sa.text("SELECT 1 FROM [core].[holding] WHERE [name] = :n"), {"n": NAME}
    ).first():
        return
    conn.execute(
        sa.text(
            """
            INSERT INTO [core].[holding]
                ([name], [side], [holding_class], [target_amount], [installment], [category_id],
                 [is_active], [sort_order], [notes])
            SELECT :n, N'asset', N'purchase', 83034.70, 3075.36, :cid, 1,
                COALESCE(MAX([sort_order]), 0) + 1,
                N'30% down payment: reserva 2,000 + entrada 25,678.22 + 18 x 3,075.36. The rest is '
                + N'financed at delivery.'
            FROM [core].[holding]
            """
        ),
        {"n": NAME, "cid": cid},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO [core].[balance_snapshot]
                ([as_of], [name], [kind], [amount], [source], [notes], [holding_id])
            SELECT '2026-11-09', [name], N'asset', 33829.94, N'manual',
                N'Reserva 2,000 + entrada 25,678.22 + 2 installments of 3,075.36', [holding_id]
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
            WHERE [name] = N'{NAME}' AND [holding_class] = N'purchase'
        )
        """
    )
    op.execute(
        f"DELETE FROM [core].[holding] WHERE [name] = N'{NAME}' AND [holding_class] = N'purchase'"
    )
    op.execute(
        f"""
        UPDATE [core].[transaction]
        SET [category_id] = NULL, [category_source] = NULL, [type] = N'expense', [is_fixed] = 0
        WHERE [category_id] IN ({CATEGORY})
        """
    )
    op.execute(
        f"DELETE FROM [core].[merchant_rule] WHERE [pattern] = N'KALANI' "
        f"AND [category_id] IN ({CATEGORY})"
    )
    op.execute(
        """
        DELETE [c] FROM [core].[category] AS [c]
        INNER JOIN [core].[category] AS [p] ON [p].[category_id] = [c].[parent_id]
        WHERE [c].[name] = N'New house' AND [p].[name] = N'Housing'
        """
    )
