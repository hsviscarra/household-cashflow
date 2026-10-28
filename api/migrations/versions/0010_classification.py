"""Classification (F9): rule amount ranges, splits, the category's origin, the change log and
Claude's suggestions; the IESS split becomes two editable rules (seed v4); the views count a
split line through its parts.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import context, op

from app.models import Category, MerchantRule
from app.seeds import load_v4, unload_v4

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)
VIEWS = ("mart.v_monthly_cashflow", "mart.v_category_month")
ROOT = Path(__file__).resolve().parent.parent / "views"


def _views(folder: Path) -> None:
    for view in VIEWS:
        schema, name = view.split(".")
        op.execute(f"DROP VIEW IF EXISTS [{schema}].[{name}];")
        op.execute((folder / f"{view}.sql").read_text(encoding="utf-8"))


def upgrade() -> None:
    op.add_column("merchant_rule", sa.Column("amount_min", MONEY, nullable=True), schema="core")
    op.add_column("merchant_rule", sa.Column("amount_max", MONEY, nullable=True), schema="core")

    op.add_column(
        "transaction",
        sa.Column(
            "parent_transaction_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.transaction.transaction_id", name="fk_transaction_parent_transaction_id"
            ),
            nullable=True,
        ),
        schema="core",
    )
    op.add_column(
        "transaction",
        sa.Column(
            "rule_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.merchant_rule.rule_id", name="fk_transaction_rule_id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        schema="core",
    )
    op.add_column(
        "transaction", sa.Column("category_source", sa.Unicode(12), nullable=True), schema="core"
    )
    op.create_check_constraint(
        "ck_transaction_category_source",
        "transaction",
        "category_source IN ('rule', 'section', 'manual', 'suggestion', 'excel', 'split')",
        schema="core",
    )
    op.create_index(
        "ix_transaction_parent_transaction_id",
        "transaction",
        ["parent_transaction_id"],
        schema="core",
    )

    op.create_table(
        "change_log",
        sa.Column("change_id", sa.Integer(), primary_key=True),
        sa.Column("table_name", sa.Unicode(60), nullable=False),
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("column_name", sa.Unicode(60), nullable=False),
        sa.Column("old_value", sa.Unicode(400), nullable=True),
        sa.Column("new_value", sa.Unicode(400), nullable=True),
        sa.Column("reason", sa.Unicode(200), nullable=False),
        sa.Column("changed_by", sa.Unicode(320), nullable=False),
        sa.Column("changed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="audit",
    )
    op.create_index("ix_change_log_row_id", "change_log", ["row_id"], schema="audit")

    op.create_table(
        "merchant_suggestion",
        sa.Column("suggestion_id", sa.Integer(), primary_key=True),
        sa.Column("merchant_key", sa.Unicode(200), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.category.category_id",
                name="fk_merchant_suggestion_category_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("reason", sa.Unicode(400), nullable=False),
        sa.Column("model", sa.Unicode(60), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("merchant_key", name="uq_merchant_suggestion_merchant_key"),
        schema="core",
    )

    # Where existing categories came from: the workbook, or the import's rule or section.
    op.execute(
        "UPDATE [t] SET [t].[rule_id] = [s].[rule_id] "
        "FROM [core].[transaction] AS [t] "
        "JOIN [stg].[stg_transaction] AS [s] ON [s].[natural_key] = [t].[natural_key] "
        "WHERE [t].[source] = 'statement' AND [s].[rule_id] IS NOT NULL;"
    )
    op.execute(
        "UPDATE [core].[transaction] SET [category_source] = CASE "
        "WHEN [source] = 'excel_history' THEN 'excel' "
        "WHEN [rule_id] IS NOT NULL THEN 'rule' "
        "WHEN [category_id] IS NOT NULL THEN 'section' END;"
    )
    _views(ROOT / "0018")  # frozen copy: the head files changed in 0019

    if context.is_offline_mode():
        op.execute("-- seed v4 (IESS amount-range rules) is loaded only in online mode")
    else:
        load_v4(op.get_bind(), Category.__table__, MerchantRule.__table__)


def downgrade() -> None:
    if not context.is_offline_mode():
        unload_v4(op.get_bind(), MerchantRule.__table__)
    # Split parts can't be represented before 0010: refuse rather than lose them.
    op.execute(
        "IF EXISTS (SELECT 1 FROM [core].[transaction] WHERE [parent_transaction_id] IS NOT NULL) "
        "THROW 50000, 'Split transactions exist; undo the splits before downgrading.', 1;"
    )
    _views(ROOT / "0008")
    op.drop_table("merchant_suggestion", schema="core")
    op.drop_index("ix_change_log_row_id", table_name="change_log", schema="audit")
    op.drop_table("change_log", schema="audit")
    op.drop_index("ix_transaction_parent_transaction_id", table_name="transaction", schema="core")
    op.drop_constraint(
        "ck_transaction_category_source", "transaction", schema="core", type_="check"
    )
    op.drop_column("transaction", "category_source", schema="core")
    op.drop_constraint("fk_transaction_rule_id", "transaction", schema="core", type_="foreignkey")
    op.drop_column("transaction", "rule_id", schema="core")
    op.drop_constraint(
        "fk_transaction_parent_transaction_id", "transaction", schema="core", type_="foreignkey"
    )
    op.drop_column("transaction", "parent_transaction_id", schema="core")
    op.drop_column("merchant_rule", "amount_max", schema="core")
    op.drop_column("merchant_rule", "amount_min", schema="core")
