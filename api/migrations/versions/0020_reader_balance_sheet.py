"""Claude may read the balance sheet, loans and saved reports (ADR-017 amended): mart_reader also
gets SELECT, and only SELECT, on the tables those are computed from. Statement lines' raw text,
merchant rules, the change log and the workbook's cells stay out.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "core.account",
    "core.transaction",
    "core.recurring_template",
    "core.recurring_amount",
    "core.recurring_entry",
    "core.holding",
    "core.balance_snapshot",
    "core.loan_installment",
    "core.monthly_report",
    "raw.statement_file",
    "raw.statement_file_account",
    "raw.statement_header",
    "stg.import_batch",
)


def _each(verb: str) -> None:
    for t in TABLES:
        schema, name = t.split(".")
        word = "TO" if verb == "GRANT" else "FROM"
        op.execute(f"{verb} SELECT ON [{schema}].[{name}] {word} [mart_reader];")


def upgrade() -> None:
    _each("GRANT")


def downgrade() -> None:
    _each("REVOKE")
