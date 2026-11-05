"""Seed v7: the fuller category tree. New groups (Insurance, Entertainment & Leisure, Education &
Career, Personal Care, Gifts & Celebrations, Family Support, Taxes), Travel renamed Travel &
Vacations with subcategories, health and dad's insurance moved to Insurance, new subcategories in
Health, Transport, Pets, Shopping, Other Income and Transfers (Held for Others, Loans to Others,
Loan Repaid to Me), descriptions and rules for merchants seen in July to October 2026. No schema
change; lines keep their category ids, so moved categories keep their lines. The read-only login
(mart_reader) may now read core.category.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.models import (
    Budget,
    Category,
    Holding,
    MerchantRule,
    RecurringTemplate,
    StgTransaction,
    Transaction,
)
from app.seeds import _category_ids, load_v7, unload_v7, v7, v7_added

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Everything that points at a category, apart from the rules seed v7 adds itself.
USERS = (Transaction, RecurringTemplate, Budget, Holding, StgTransaction)


GRANT = "GRANT SELECT ON [core].[category] TO [mart_reader];"


def upgrade() -> None:
    # Data Status (and Claude's data_status tool, read-only login) tells transfers that need an
    # other side from money held for others by their category: the reader needs the names.
    op.execute(GRANT)
    if context.is_offline_mode():
        op.execute("-- seed v7 (category tree) is loaded only in online mode")
        return
    load_v7(op.get_bind(), Category.__table__, MerchantRule.__table__)


def in_use(conn: sa.Connection) -> bool:
    """Whether anything Hernan made uses a category seed v7 added (the unload would lose it)."""
    added = v7_added(conn, Category.__table__)
    if not added:
        return False
    # Seed v7's own rules and the rules and categories it moved go back with the unload.
    patterns = [p for p, *_ in v7.MERCHANT_RULES] + [p for p, *_ in v7.RULE_MOVES]
    ids = _category_ids(conn, Category.__table__)
    moved = [ids[f"{g}/{n}"] for _p, g, n in v7.MOVES if f"{g}/{n}" in ids]
    rule = MerchantRule.__table__
    cat = Category.__table__
    checks = [
        sa.select(m.__table__.c.category_id).where(m.__table__.c.category_id.in_(added))
        for m in USERS
    ]
    checks.append(
        sa.select(rule.c.rule_id).where(
            rule.c.category_id.in_(added), rule.c.pattern.not_in(patterns)
        )
    )
    checks.append(
        sa.select(cat.c.category_id).where(
            cat.c.parent_id.in_(added), cat.c.category_id.not_in([*added, *moved])
        )
    )
    return any(conn.execute(q.limit(1)).first() is not None for q in checks)


def downgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- seed v7 (category tree) is unloaded only in online mode")
        op.execute(GRANT.replace("GRANT", "REVOKE").replace(" TO ", " FROM "))
        return
    conn = op.get_bind()
    if in_use(conn):
        raise RuntimeError(
            "Seed v7's categories are in use (lines, rules, recurring items or new "
            "subcategories): move them to other categories before downgrading."
        )
    unload_v7(conn, Category.__table__, MerchantRule.__table__)
    op.execute(GRANT.replace("GRANT", "REVOKE").replace(" TO ", " FROM "))
