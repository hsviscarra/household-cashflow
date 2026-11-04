"""Produbanco Visa (seed v6): Hernan's credit card ending 5997, read by the Produbanco reader
(statements "Estado de Cuenta Produbanco - Grupo Promerica", emailed from bancaenlinea@
produbanco.com), plus a rule for Megadatos (Netlife). Same source as the savings statements
("produbanco"), so the statement source check is unchanged.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import context, op

from app.models import Account, Category, MerchantRule
from app.seeds import load_v6, unload_v6

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("-- seed v6 (Produbanco Visa account and rule) is loaded only in online mode")
        return
    load_v6(op.get_bind(), Account.__table__, Category.__table__, MerchantRule.__table__)


def downgrade() -> None:
    # Statements or lines already loaded for the card would lose their account: refuse.
    op.execute(
        "IF EXISTS (SELECT 1 FROM [core].[account] AS [a] "
        "WHERE [a].[name] = 'Produbanco Visa' AND ("
        "EXISTS (SELECT 1 FROM [core].[transaction] AS [t] "
        "WHERE [t].[account_id] = [a].[account_id]) "
        "OR EXISTS (SELECT 1 FROM [raw].[statement_file_account] AS [s] "
        "WHERE [s].[account_id] = [a].[account_id]))) "
        "THROW 50000, 'Produbanco Visa has statements; remove them before downgrading.', 1;"
    )
    if not context.is_offline_mode():
        unload_v6(op.get_bind(), Account.__table__, MerchantRule.__table__)
