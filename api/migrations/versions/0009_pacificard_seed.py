"""Pacificard (F8b): a new statement source, its account and rules for its charges.

Schema: raw.statement_file's source check gains 'pacificard'. Data: seed v3.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-21
"""

from collections.abc import Sequence

from alembic import context, op

from app.models import Account, Category, MerchantRule
from app.seeds import load_v3, unload_v3

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCES = ("bofa", "capitalone", "pichincha", "produbanco", "diners", "unknown")
NEW = "pacificard"


def _source_check(sources: tuple[str, ...]) -> None:
    op.drop_constraint("ck_statement_file_source", "statement_file", schema="raw", type_="check")
    listed = ", ".join(f"'{s}'" for s in sources)
    op.create_check_constraint(
        "ck_statement_file_source", "statement_file", f"source IN ({listed})", schema="raw"
    )


def upgrade() -> None:
    _source_check((*SOURCES, NEW))
    if context.is_offline_mode():
        op.execute("-- seed v3 (Pacificard account and rules) is loaded only in online mode")
        return
    load_v3(op.get_bind(), Account.__table__, Category.__table__, MerchantRule.__table__)


def downgrade() -> None:
    # Statements already uploaded from the new source would break the old check: refuse.
    op.execute(
        f"IF EXISTS (SELECT 1 FROM [raw].[statement_file] WHERE [source] = '{NEW}') "
        "THROW 50000, 'Pacificard statements exist; remove them before downgrading.', 1;"
    )
    if not context.is_offline_mode():
        unload_v3(op.get_bind(), Account.__table__, MerchantRule.__table__)
    _source_check(SOURCES)
