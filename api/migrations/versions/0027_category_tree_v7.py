"""Seed v7: the fuller category tree. New groups (Insurance, Entertainment & Leisure, Education &
Career, Personal Care, Gifts & Celebrations, Family Support, Taxes), Travel renamed Travel &
Vacations with subcategories, health and dad's insurance moved to Insurance, new subcategories in
Health, Transport, Pets, Shopping, Other Income and Transfers (Held for Others, Loans to Others,
Loan Repaid to Me), descriptions and rules for merchants seen in July to October 2026. No schema
change; lines keep their category ids, so moved categories keep their lines.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.models import Category, MerchantRule
from app.seeds import load_v7, unload_v7, v7, v7_added

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Everything that points at a category, apart from the rules seed v7 adds itself.
USERS = (
    ("core", "transaction"),
    ("core", "recurring_template"),
    ("core", "budget"),
    ("core", "holding"),
    ("stg", "stg_transaction"),
)


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- seed v7 (category tree) is loaded only in online mode")
        return
    load_v7(op.get_bind(), Category.__table__, MerchantRule.__table__)


def downgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- seed v7 (category tree) is unloaded only in online mode")
        return
    conn = op.get_bind()
    added = v7_added(conn, Category.__table__)
    if added:
        listed = ", ".join(str(i) for i in added)
        seeded = ", ".join("'" + p.replace("'", "''") + "'" for p, *_ in v7.MERCHANT_RULES)
        checks = [f"SELECT 1 FROM [{s}].[{t}] WHERE [category_id] IN ({listed})" for s, t in USERS]
        checks.append(
            f"SELECT 1 FROM [core].[merchant_rule] WHERE [category_id] IN ({listed}) "
            f"AND [pattern] NOT IN ({seeded})"
        )
        checks.append(
            f"SELECT 1 FROM [core].[category] WHERE [parent_id] IN ({listed}) "
            f"AND [category_id] NOT IN ({listed})"
        )
        for sql in checks:
            if conn.execute(sa.text(sql)).first() is not None:
                raise RuntimeError(
                    "Seed v7's categories are in use (lines, rules, recurring items or new "
                    "subcategories): move them to other categories before downgrading."
                )
    unload_v7(conn, Category.__table__, MerchantRule.__table__)
