"""People and transfer notes (ADR-023): core.counterparty (who a line's money belongs to or was
for, with patterns found in statement descriptions, a category and an optional balance item),
core.transfer_note (a transfer told to the app, matched to its statement line) and
core.transaction.counterparty_id; "note" and "person" as category sources. The read-only login
may read both tables (names, amounts and descriptions; no account numbers are stored).

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Data Status (and Claude's data_status) reads the notes still without a line.
READER = ("counterparty", "transfer_note")
SOURCES = ("rule", "section", "manual", "suggestion", "excel", "split", "match")


def _sources(values: tuple[str, ...]) -> None:
    op.drop_constraint(
        "ck_transaction_category_source", "transaction", schema="core", type_="check"
    )
    listed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(
        "ck_transaction_category_source",
        "transaction",
        f"category_source IN ({listed})",
        schema="core",
    )


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "counterparty",
        sa.Column("counterparty_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("patterns", sa.Unicode(400), nullable=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_counterparty_category_id"),
            nullable=True,
        ),
        sa.Column(
            "holding_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.holding.holding_id",
                name="fk_counterparty_holding_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("notes", sa.Unicode(400), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_counterparty_name"),
        schema="core",
    )
    op.add_column(
        "transaction",
        sa.Column(
            "counterparty_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.counterparty.counterparty_id",
                name="fk_transaction_counterparty_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        schema="core",
    )
    op.create_index(
        "ix_transaction_counterparty_id", "transaction", ["counterparty_id"], schema="core"
    )
    op.create_table(
        "transfer_note",
        sa.Column("note_id", sa.Integer(), primary_key=True),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("core.account.account_id", name="fk_transfer_note_account_id"),
            nullable=True,
        ),
        sa.Column(
            "counterparty_id",
            sa.Integer(),
            # No cascade: SQL Server refuses a second cascade path to core.counterparty; the app
            # clears it before a person is deleted.
            sa.ForeignKey(
                "core.counterparty.counterparty_id", name="fk_transfer_note_counterparty_id"
            ),
            nullable=True,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("core.category.category_id", name="fk_transfer_note_category_id"),
            nullable=True,
        ),
        sa.Column("other_party", sa.Unicode(100), nullable=True),
        sa.Column("description", sa.Unicode(400), nullable=True),
        sa.Column("source", sa.Unicode(10), server_default="manual", nullable=False),
        sa.Column("reference", sa.Unicode(64), nullable=True),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey(
                "core.transaction.transaction_id", name="fk_transfer_note_transaction_id"
            ),
            nullable=True,
        ),
        sa.Column("created_by", sa.Unicode(320), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("source IN ('manual', 'email')", name="ck_transfer_note_source"),
        schema="core",
    )
    op.create_index("ix_transfer_note_reference", "transfer_note", ["reference"], schema="core")
    op.create_index(
        "ix_transfer_note_transaction_id", "transfer_note", ["transaction_id"], schema="core"
    )
    _sources((*SOURCES, "note", "person"))
    for table in READER:
        op.execute(f"GRANT SELECT ON [core].[{table}] TO [mart_reader];")


def downgrade() -> None:
    for table in READER:
        op.execute(f"REVOKE SELECT ON [core].[{table}] FROM [mart_reader];")
    op.execute(
        "UPDATE [core].[transaction] SET [category_source] = 'manual' "
        "WHERE [category_source] IN ('note', 'person');"
    )
    _sources(SOURCES)
    op.drop_index("ix_transfer_note_transaction_id", table_name="transfer_note", schema="core")
    op.drop_index("ix_transfer_note_reference", table_name="transfer_note", schema="core")
    op.drop_table("transfer_note", schema="core")
    op.drop_index("ix_transaction_counterparty_id", table_name="transaction", schema="core")
    op.drop_constraint(
        "fk_transaction_counterparty_id", "transaction", schema="core", type_="foreignkey"
    )
    op.drop_column("transaction", "counterparty_id", schema="core")
    op.drop_table("counterparty", schema="core")
