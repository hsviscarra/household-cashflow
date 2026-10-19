"""Baseline: one schema per pipeline stage.

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# [audit] is created by migrations/env.py because it holds the alembic version table.
SCHEMAS = ("raw", "stg", "rej", "core", "mart")


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f"IF SCHEMA_ID(N'{schema}') IS NULL EXEC(N'CREATE SCHEMA [{schema}]');")


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f"IF SCHEMA_ID(N'{schema}') IS NOT NULL DROP SCHEMA [{schema}];")
