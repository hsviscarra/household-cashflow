"""History and transactions (F2): raw workbook cells, core.transaction, budget, balance snapshots,
audit.load_log, seed v2 categories and the first mart views.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import context, op

from app.models import Category
from app.seeds import load_v2, unload_v2

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEWS = ("mart.v_monthly_cashflow", "mart.v_category_month")
VIEW_DIR = Path(__file__).resolve().parent.parent / "views"
MONEY = sa.Numeric(19, 4)


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "excel_import",
        sa.Column("import_id", sa.Integer(), primary_key=True),
        sa.Column("file_sha256", sa.Unicode(64), nullable=False),
        sa.Column("file_name", sa.Unicode(260), nullable=False),
        sa.Column("loaded_by", sa.Unicode(320), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("file_sha256", name="uq_excel_import_file_sha256"),
        schema="raw",
    )
    op.create_table(
        "excel_cell",
        sa.Column("cell_id", sa.Integer(), primary_key=True),
        sa.Column(
            "import_id",
            sa.Integer(),
            sa.ForeignKey("raw.excel_import.import_id", name="fk_excel_cell_import_id"),
            nullable=False,
        ),
        sa.Column("sheet", sa.Unicode(60), nullable=False),
        sa.Column("cell", sa.Unicode(10), nullable=False),
        sa.Column("block", sa.Unicode(30), nullable=False),
        sa.Column("group_label", sa.Unicode(100), nullable=True),
        sa.Column("row_label", sa.Unicode(100), nullable=False),
        sa.Column("month", sa.Date(), nullable=True),
        sa.Column("value", MONEY, nullable=False),
        schema="raw",
    )
    op.create_table(
        "transaction",
        sa.Column("transaction_id", sa.Integer(), primary_key=True),
        sa.Column("natural_key", sa.Unicode(64), nullable=False),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("core.account.account_id", name="fk_transaction_account_id"),
            nullable=True,
        ),
        sa.Column(
            "excel_cell_id",
            sa.Integer(),
            sa.ForeignKey("raw.excel_cell.cell_id", name="fk_transaction_excel_cell_id"),
            nullable=True,
        ),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("cash_month", sa.Date(), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("description_raw", sa.Unicode(400), nullable=False),
        sa.Column("merchant", sa.Unicode(200), nullable=True),
        sa.Column("pay_reference", sa.Unicode(100), nullable=True),
        sa.Column("notes", sa.Unicode(1000), nullable=True),
        sa.Column("type", sa.Unicode(12), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_transaction_category_id"),
            nullable=True,
        ),
        sa.Column("person", sa.Unicode(10), nullable=True),
        sa.Column("country", sa.Unicode(2), nullable=True),
        sa.Column("is_fixed", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.Unicode(15), nullable=False),
        sa.Column("status", sa.Unicode(10), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "type IN ('income', 'expense', 'savings', 'transfer', 'refund', 'fee_interest', "
            "'debt_payment')",
            name="ck_transaction_type",
        ),
        sa.CheckConstraint(
            "source IN ('statement', 'manual', 'excel_history')", name="ck_transaction_source"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'matched')", name="ck_transaction_status"
        ),
        sa.UniqueConstraint("natural_key", name="uq_transaction_natural_key"),
        schema="core",
    )
    op.create_index("ix_transaction_cash_month", "transaction", ["cash_month"], schema="core")
    op.create_table(
        "budget",
        sa.Column("budget_id", sa.Integer(), primary_key=True),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_budget_category_id"),
            nullable=False,
        ),
        sa.Column("label", sa.Unicode(100), nullable=False),
        sa.Column("type", sa.Unicode(12), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("source", sa.Unicode(20), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("month", "category_id", "label", "source", name="uq_budget_month"),
        schema="core",
    )
    op.create_table(
        "balance_snapshot",
        sa.Column("snapshot_id", sa.Integer(), primary_key=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("kind", sa.Unicode(10), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("core.account.account_id", name="fk_balance_snapshot_account_id"),
            nullable=True,
        ),
        sa.Column("source", sa.Unicode(20), nullable=False),
        sa.Column("notes", sa.Unicode(400), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('asset', 'liability')", name="ck_balance_snapshot_kind"),
        sa.UniqueConstraint("as_of", "name", "source", name="uq_balance_snapshot_as_of"),
        schema="core",
    )
    op.create_table(
        "load_log",
        sa.Column("load_id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.Unicode(30), nullable=False),
        sa.Column("file_sha256", sa.Unicode(64), nullable=True),
        sa.Column("loaded_by", sa.Unicode(320), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("rows_loaded", sa.Integer(), nullable=False),
        sa.Column("summary", sa.UnicodeText(), nullable=False),
        schema="audit",
    )

    for view in VIEWS:
        op.execute((VIEW_DIR / f"{view}.sql").read_text(encoding="utf-8"))

    if context.is_offline_mode():
        op.execute("-- seed v2 categories are loaded only in online mode")
    else:
        load_v2(op.get_bind(), Category.__table__)


def downgrade() -> None:
    for view in reversed(VIEWS):
        schema, name = view.split(".")
        op.execute(f"DROP VIEW IF EXISTS [{schema}].[{name}];")
    op.drop_table("load_log", schema="audit")
    op.drop_table("balance_snapshot", schema="core")
    op.drop_table("budget", schema="core")
    op.drop_index("ix_transaction_cash_month", table_name="transaction", schema="core")
    op.drop_table("transaction", schema="core")
    op.drop_table("excel_cell", schema="raw")
    op.drop_table("excel_import", schema="raw")
    # Categories last: the dropped tables referenced them.
    if not context.is_offline_mode():
        unload_v2(op.get_bind(), Category.__table__)
