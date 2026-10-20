"""Uploaded statements (F3): raw.statement_file and raw.statement_file_account.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "statement_file",
        sa.Column("statement_file_id", sa.Integer(), primary_key=True),
        sa.Column("sha256", sa.Unicode(64), nullable=False),
        sa.Column("file_name", sa.Unicode(260), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("source", sa.Unicode(12), nullable=False),
        sa.Column("status", sa.Unicode(15), nullable=False),
        sa.Column("last4_found", sa.Unicode(60), nullable=True),
        sa.Column("account_match", sa.Unicode(10), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("blob_key", sa.Unicode(200), nullable=False),
        sa.Column("uploaded_by", sa.Unicode(320), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "source IN ('bofa', 'capitalone', 'pichincha', 'produbanco', 'diners', 'unknown')",
            name="ck_statement_file_source",
        ),
        sa.CheckConstraint(
            "status IN ('detected', 'needs_account', 'unknown_format')",
            name="ck_statement_file_status",
        ),
        sa.UniqueConstraint("sha256", name="uq_statement_file_sha256"),
        schema="raw",
    )
    op.create_table(
        "statement_file_account",
        sa.Column(
            "statement_file_id",
            sa.Integer(),
            sa.ForeignKey(
                "raw.statement_file.statement_file_id",
                name="fk_statement_file_account_statement_file_id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("core.account.account_id", name="fk_statement_file_account_account_id"),
            primary_key=True,
        ),
        schema="raw",
    )


def downgrade() -> None:
    op.drop_table("statement_file_account", schema="raw")
    op.drop_table("statement_file", schema="raw")
