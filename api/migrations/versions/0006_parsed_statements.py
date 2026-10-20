"""Parsed statements (F4): raw.statement_header, raw.raw_line, stg.import_batch,
stg.stg_transaction, rej.rejected_line, and statement links on core.transaction.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)


def _fk_statement(name: str, cascade: bool = True) -> sa.Column[int]:
    return sa.Column(
        "statement_file_id",
        sa.Integer(),
        sa.ForeignKey(
            "raw.statement_file.statement_file_id",
            name=name,
            ondelete="CASCADE" if cascade else None,
        ),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "statement_header",
        sa.Column(
            "statement_file_id",
            sa.Integer(),
            sa.ForeignKey(
                "raw.statement_file.statement_file_id",
                name="fk_statement_header_statement_file_id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
        sa.Column("parser", sa.Unicode(30), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("opening_balance", MONEY, nullable=True),
        sa.Column("closing_balance", MONEY, nullable=True),
        sa.Column("totals_json", sa.UnicodeText(), nullable=False),
        sa.Column("parsed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="raw",
    )
    op.create_table(
        "raw_line",
        sa.Column("raw_line_id", sa.Integer(), primary_key=True),
        _fk_statement("fk_raw_line_statement_file_id"),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("section", sa.Unicode(30), nullable=False),
        sa.Column("cardholder", sa.Unicode(10), nullable=True),
        sa.Column("text", sa.Unicode(400), nullable=False),
        sa.Column("data_json", sa.UnicodeText(), nullable=False),
        schema="raw",
    )
    op.create_index(
        "ix_raw_line_statement_file_id", "raw_line", ["statement_file_id"], schema="raw"
    )
    op.create_table(
        "import_batch",
        sa.Column("batch_id", sa.Integer(), primary_key=True),
        _fk_statement("fk_import_batch_statement_file_id", cascade=False),
        sa.Column("status", sa.Unicode(10), nullable=False),
        sa.Column("tieout_ok", sa.Boolean(), nullable=False),
        sa.Column("checks_json", sa.UnicodeText(), nullable=False),
        sa.Column("created_by", sa.Unicode(320), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_by", sa.Unicode(320), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('preview', 'approved', 'rejected')", name="ck_import_batch_status"
        ),
        schema="stg",
    )
    op.create_index(
        "ix_import_batch_statement_file_id", "import_batch", ["statement_file_id"], schema="stg"
    )
    op.create_table(
        "stg_transaction",
        sa.Column("stg_id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey(
                "stg.import_batch.batch_id",
                name="fk_stg_transaction_batch_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "raw_line_id",
            sa.Integer(),
            sa.ForeignKey("raw.raw_line.raw_line_id", name="fk_stg_transaction_raw_line_id"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("core.account.account_id", name="fk_stg_transaction_account_id"),
            nullable=False,
        ),
        sa.Column("natural_key", sa.Unicode(64), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("post_date", sa.Date(), nullable=True),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("description_raw", sa.Unicode(400), nullable=False),
        sa.Column("merchant", sa.Unicode(200), nullable=True),
        sa.Column("type", sa.Unicode(12), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_stg_transaction_category_id"),
            nullable=True,
        ),
        sa.Column(
            "rule_id",
            sa.Integer(),
            sa.ForeignKey("core.merchant_rule.rule_id", name="fk_stg_transaction_rule_id"),
            nullable=True,
        ),
        sa.Column("person", sa.Unicode(10), nullable=True),
        sa.Column("country", sa.Unicode(2), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False),
        schema="stg",
    )
    op.create_index("ix_stg_transaction_batch_id", "stg_transaction", ["batch_id"], schema="stg")
    op.create_table(
        "rejected_line",
        sa.Column("rejected_id", sa.Integer(), primary_key=True),
        _fk_statement("fk_rejected_line_statement_file_id"),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Unicode(400), nullable=False),
        sa.Column("reason", sa.Unicode(200), nullable=False),
        schema="rej",
    )
    op.create_index(
        "ix_rejected_line_statement_file_id", "rejected_line", ["statement_file_id"], schema="rej"
    )

    op.add_column(
        "transaction",
        sa.Column(
            "statement_file_id",
            sa.Integer(),
            sa.ForeignKey(
                "raw.statement_file.statement_file_id",
                name="fk_transaction_statement_file_id",
            ),
            nullable=True,
        ),
        schema="core",
    )
    op.add_column(
        "transaction",
        sa.Column(
            "raw_line_id",
            sa.Integer(),
            sa.ForeignKey("raw.raw_line.raw_line_id", name="fk_transaction_raw_line_id"),
            nullable=True,
        ),
        schema="core",
    )
    op.add_column(
        "transaction",
        sa.Column(
            "import_batch_id",
            sa.Integer(),
            sa.ForeignKey("stg.import_batch.batch_id", name="fk_transaction_import_batch_id"),
            nullable=True,
        ),
        schema="core",
    )
    op.add_column("transaction", sa.Column("post_date", sa.Date(), nullable=True), schema="core")


def downgrade() -> None:
    for column in ("import_batch_id", "raw_line_id", "statement_file_id"):
        op.drop_constraint(f"fk_transaction_{column}", "transaction", schema="core")
        op.drop_column("transaction", column, schema="core")
    op.drop_column("transaction", "post_date", schema="core")
    op.drop_index("ix_rejected_line_statement_file_id", table_name="rejected_line", schema="rej")
    op.drop_table("rejected_line", schema="rej")
    op.drop_index("ix_stg_transaction_batch_id", table_name="stg_transaction", schema="stg")
    op.drop_table("stg_transaction", schema="stg")
    op.drop_index("ix_import_batch_statement_file_id", table_name="import_batch", schema="stg")
    op.drop_table("import_batch", schema="stg")
    op.drop_index("ix_raw_line_statement_file_id", table_name="raw_line", schema="raw")
    op.drop_table("raw_line", schema="raw")
    op.drop_table("statement_header", schema="raw")
