"""Investment positions (F22, ADR-019): core.investment_position, each day's positions of an
investment holding read from the broker. The day's total goes to core.balance_snapshot (source
'ibkr') like any other value.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(19, 4)
QTY = sa.Numeric(19, 6)


def upgrade() -> None:
    op.create_table(
        "investment_position",
        sa.Column("position_id", sa.Integer(), primary_key=True),
        sa.Column(
            "holding_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.holding.holding_id",
                name="fk_investment_position_holding_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("symbol", sa.Unicode(40), nullable=False),
        sa.Column("description", sa.Unicode(200), nullable=True),
        sa.Column("asset_class", sa.Unicode(20), nullable=False),
        sa.Column("currency", sa.Unicode(3), nullable=False),
        sa.Column("quantity", QTY, nullable=False),
        sa.Column("price", QTY, nullable=False),
        sa.Column("value", MONEY, nullable=False),
        sa.Column("cost_basis", MONEY, nullable=True),
        sa.Column("unrealized", MONEY, nullable=True),
        sa.UniqueConstraint(
            "holding_id", "as_of", "symbol", "asset_class", name="uq_investment_position_holding_id"
        ),
        schema="core",
    )
    op.create_index(
        "ix_investment_position_holding_id", "investment_position", ["holding_id"], schema="core"
    )
    # Claude's read-only login reads it with the balance sheet (ADR-017).
    op.execute("GRANT SELECT ON [core].[investment_position] TO [mart_reader];")


def downgrade() -> None:
    op.execute("DELETE FROM [core].[balance_snapshot] WHERE [source] = 'ibkr';")
    op.execute("REVOKE SELECT ON [core].[investment_position] FROM [mart_reader];")
    op.drop_index(
        "ix_investment_position_holding_id", table_name="investment_position", schema="core"
    )
    op.drop_table("investment_position", schema="core")
