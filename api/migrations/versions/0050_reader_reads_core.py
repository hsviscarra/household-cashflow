"""Claude reads every page (ADR-069, ADR-072 amended): mart_reader gets SELECT, and only SELECT,
on the whole core schema and on audit.load_log. The tools for taxes, IVA, groceries, bills and
budget, and the bank-sync coverage in data status and the balance sheet, read tables that 0020 to
0028 never listed (budget plans, goals, tax profiles, settings, the load log), so they failed
under the read-only login. Statement lines as printed (raw), staging, the workbook's cells and the
change log stay out.

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON SCHEMA::[core] TO [mart_reader];")
    op.execute("GRANT SELECT ON [audit].[load_log] TO [mart_reader];")


def downgrade() -> None:
    # The table-by-table grants of 0020 to 0028 stay as they were.
    op.execute("REVOKE SELECT ON [audit].[load_log] FROM [mart_reader];")
    op.execute("REVOKE SELECT ON SCHEMA::[core] FROM [mart_reader];")
