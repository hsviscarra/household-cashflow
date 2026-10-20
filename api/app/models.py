"""SQLAlchemy models for the core reference tables (F1).

Generic column types keep the models portable: Unicode -> NVARCHAR and Boolean -> BIT on SQL Server,
while unit tests run the same models on SQLite.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Unicode,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ACCOUNT_KINDS = ("checking", "savings", "credit_card")
OWNERS = ("Hernan", "Lauren", "Joint")
COUNTRIES = ("US", "EC")
CATEGORY_KINDS = ("income", "expense", "savings", "transfer")
MATCH_TYPES = ("contains", "starts_with", "regex")

NAMING = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
}


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Account(Timestamps, Base):
    __tablename__ = "account"
    __table_args__ = (
        CheckConstraint(_in("kind", ACCOUNT_KINDS), name="kind"),
        CheckConstraint(_in("owner", OWNERS), name="owner"),
        CheckConstraint(_in("country", COUNTRIES), name="country"),
        UniqueConstraint("name"),
        {"schema": "core"},
    )

    account_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    institution: Mapped[str] = mapped_column(Unicode(100))
    kind: Mapped[str] = mapped_column(Unicode(20))
    owner: Mapped[str] = mapped_column(Unicode(10))
    country: Mapped[str] = mapped_column(Unicode(2))
    # Last four digits only; full account and card numbers are never stored.
    last4: Mapped[str | None] = mapped_column(Unicode(4))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class Category(Timestamps, Base):
    __tablename__ = "category"
    __table_args__ = (
        CheckConstraint(_in("kind", CATEGORY_KINDS), name="kind"),
        UniqueConstraint("parent_id", "name"),
        {"schema": "core"},
    )

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))
    name: Mapped[str] = mapped_column(Unicode(100))
    kind: Mapped[str] = mapped_column(Unicode(10))
    # Hex color for charts and chips; subcategories inherit their group's color when null.
    color: Mapped[str | None] = mapped_column(Unicode(7))
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    parent: Mapped["Category | None"] = relationship(remote_side=[category_id])


class MerchantRule(Timestamps, Base):
    __tablename__ = "merchant_rule"
    __table_args__ = (
        CheckConstraint(_in("match_type", MATCH_TYPES), name="match_type"),
        {"schema": "core"},
    )

    rule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(Unicode(200))
    match_type: Mapped[str] = mapped_column(Unicode(12), default="contains")
    category_id: Mapped[int] = mapped_column(ForeignKey("core.category.category_id"))
    # Lower runs first; the first matching active rule wins.
    priority: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    category: Mapped[Category] = relationship()
