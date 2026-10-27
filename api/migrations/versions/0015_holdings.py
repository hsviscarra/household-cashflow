"""Balance sheet (F14, ADR-012): core.holding, one row per thing owned or owed, and the link from
each balance snapshot to its holding. The workbook's snapshots (debts, savings, what is left to
pay the lenders) become holdings.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)
CLASSES = (
    "'property', 'vehicle', 'investment', 'cash', 'purchase', 'loan', 'personal_loan', 'card', "
    "'other'"
)


def upgrade() -> None:
    op.create_table(
        "holding",
        sa.Column("holding_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("side", sa.Unicode(10), nullable=False),
        sa.Column("holding_class", sa.Unicode(15), nullable=False),
        sa.Column("target_amount", MONEY, nullable=True),
        sa.Column("installment", MONEY, nullable=True),
        sa.Column("full_price", MONEY, nullable=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_holding_category_id"),
            nullable=True,
        ),
        sa.Column(
            "recurring_template_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.recurring_template.template_id",
                name="fk_holding_recurring_template_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Unicode(400), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("side IN ('asset', 'liability')", name="ck_holding_side"),
        sa.CheckConstraint(f"holding_class IN ({CLASSES})", name="ck_holding_holding_class"),
        sa.UniqueConstraint("name", name="uq_holding_name"),
        schema="core",
    )
    op.add_column(
        "balance_snapshot", sa.Column("holding_id", sa.Integer(), nullable=True), schema="core"
    )
    op.create_foreign_key(
        "fk_balance_snapshot_holding_id",
        "balance_snapshot",
        "holding",
        ["holding_id"],
        ["holding_id"],
        source_schema="core",
        referent_schema="core",
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_balance_snapshot_holding_id", "balance_snapshot", ["holding_id"], schema="core"
    )
    # The workbook's snapshots become holdings (one per name), then point to them.
    op.execute(
        """
        INSERT INTO [core].[holding] ([name], [side], [holding_class], [sort_order])
        SELECT
            [s].[name],
            MIN([s].[kind]),
            CASE
                WHEN [s].[name] LIKE '%BIESS%' THEN 'loan'
                WHEN [s].[name] LIKE 'Remaining to pay%' THEN 'personal_loan'
                WHEN MIN([s].[kind]) = 'liability' THEN 'card'
                WHEN [s].[name] LIKE '%Stock%' THEN 'investment'
                ELSE 'cash'
            END,
            0
        FROM [core].[balance_snapshot] AS [s]
        GROUP BY [s].[name];
        """
    )
    op.execute(
        """
        UPDATE [s]
        SET [s].[holding_id] = [h].[holding_id]
        FROM [core].[balance_snapshot] AS [s]
        JOIN [core].[holding] AS [h]
            ON [h].[name] = [s].[name];
        """
    )


def downgrade() -> None:
    # Snapshots entered on the page (not from the workbook) have no place before 0015.
    op.execute("DELETE FROM [core].[balance_snapshot] WHERE [source] <> 'excel';")
    op.drop_index("ix_balance_snapshot_holding_id", table_name="balance_snapshot", schema="core")
    op.drop_constraint(
        "fk_balance_snapshot_holding_id", "balance_snapshot", schema="core", type_="foreignkey"
    )
    op.drop_column("balance_snapshot", "holding_id", schema="core")
    op.drop_table("holding", schema="core")
