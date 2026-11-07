"""Rules that do more than set a category (ADR-042): a rule can also set whose line it is and the
merchant's name.

core.merchant_rule.set_person: Hernan, Lauren or Joint; empty = the account owner, as before.
core.merchant_rule.merchant_name: the name lines get; empty = the rule's pattern, as before.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("merchant_rule", sa.Column("set_person", sa.Unicode(10)), schema="core")
    op.add_column("merchant_rule", sa.Column("merchant_name", sa.Unicode(100)), schema="core")
    op.create_check_constraint(
        "ck_merchant_rule_set_person",
        "merchant_rule",
        "set_person IS NULL OR set_person IN ('Hernan', 'Lauren', 'Joint')",
        schema="core",
    )


def downgrade() -> None:
    op.drop_constraint("ck_merchant_rule_set_person", "merchant_rule", schema="core", type_="check")
    op.drop_column("merchant_rule", "merchant_name", schema="core")
    op.drop_column("merchant_rule", "set_person", schema="core")
