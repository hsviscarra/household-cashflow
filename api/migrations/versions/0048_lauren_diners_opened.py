"""Lauren's Diners card opened in September 2026 (ADR-071): Hernan, Nov 11 2026, "I think in
September". Data Status stops asking for its August statement. Changes nothing a person set.

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WHERE = "[name] = N'Diners Club Lauren'"


def upgrade() -> None:
    op.execute(
        "UPDATE [core].[account] SET [opened_on] = '2026-09-01' "
        f"WHERE {WHERE} AND [opened_on] IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE [core].[account] SET [opened_on] = NULL "
        f"WHERE {WHERE} AND [opened_on] = '2026-09-01'"
    )
