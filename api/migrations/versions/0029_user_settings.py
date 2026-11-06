"""Per-person settings (ADR-026): core.user_setting holds each signed-in person's choices as JSON
(the Both/Hernan/Lauren switch, table columns and row size, saved views, Home widgets). Keyed by
the sign-in email ("local" without sign-in); no financial data. The read-only login gets no
access.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_setting",
        sa.Column("user_email", sa.Unicode(254), nullable=False),
        sa.Column("key", sa.Unicode(100), nullable=False),
        sa.Column("value_json", sa.UnicodeText(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_email", "key", name="pk_user_setting"),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("user_setting", schema="core")
