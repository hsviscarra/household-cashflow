"""SQLAlchemy models: reference tables (F1), history, transactions and snapshots (F2).

Generic column types keep the models portable: Unicode -> NVARCHAR and Boolean -> BIT on SQL Server,
while unit tests run the same models on SQLite.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    Table,
    Unicode,
    UnicodeText,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

ACCOUNT_KINDS = ("checking", "savings", "credit_card")
OWNERS = ("Hernan", "Lauren", "Joint")
COUNTRIES = ("US", "EC")
CATEGORY_KINDS = ("income", "expense", "savings", "transfer", "debt")  # debt: ADR-054
MATCH_TYPES = ("contains", "starts_with", "regex")
TXN_TYPES = ("income", "expense", "savings", "transfer", "refund", "fee_interest", "debt_payment")
TXN_SOURCES = ("statement", "manual", "excel_history", "bank_sync")
# Lines that come from a bank: a statement, or the daily bank sync before its statement (ADR-044).
FROM_BANKS = ("statement", "bank_sync")
TXN_STATUSES = ("pending", "confirmed", "matched")
# How a line got its category (F9): a merchant rule, the statement section, Hernan's choice, an
# accepted Claude suggestion, the Excel history, a split of a parent line, or a matched transfer
# (F10).
CATEGORY_SOURCES = (
    "rule",
    "section",
    "manual",
    "suggestion",
    "excel",
    "split",
    "match",
    "note",
    "person",
    "invoice",  # its invoice's products decided (ADR-066)
)
NOTE_SOURCES = ("manual", "email")
SNAPSHOT_KINDS = ("asset", "liability")
# F14 balance sheet: what each holding is (ADR-012).
HOLDING_CLASSES = (
    "property",
    "vehicle",
    "investment",
    "cash",
    "purchase",
    "loan",
    "personal_loan",
    "card",
    "other",
)
# F11: where a recurring template came from, and an entry's state (matched is derived from links).
RECURRING_SOURCES = ("manual", "excel")
ENTRY_STATUSES = ("planned", "skipped")
STATEMENT_SOURCES = (
    "bofa",
    "capitalone",
    "pichincha",
    "produbanco",
    "diners",
    "pacificard",
    "unknown",
)
STATEMENT_STATUSES = ("detected", "needs_account", "unknown_format")
ACCOUNT_MATCHES = ("last4", "by_bank", "manual")
BATCH_STATUSES = ("preview", "approved", "rejected")

# Money is DECIMAL(19,4) everywhere; never float.
Money = Numeric(19, 4, asdecimal=True)

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
    # The SimpleFIN account this one is fed by (ADR-044): an opaque id, not an account number.
    sync_id: Mapped[str | None] = mapped_column(Unicode(100))  # unique when set (0035)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Closed or suspended on this day (a card cancelled in September): month status stops
    # expecting statements after it, while its earlier statements still load.
    closed_on: Mapped[date | None] = mapped_column(Date)
    opened_on: Mapped[date | None] = mapped_column(Date)  # no statements expected before


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
    # What goes here (F23): shown in the category picker and sent with Claude's suggestions.
    description: Mapped[str | None] = mapped_column(Unicode(400))
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    parent: Mapped["Category | None"] = relationship(remote_side=[category_id])


class MerchantRule(Timestamps, Base):
    __tablename__ = "merchant_rule"
    __table_args__ = (
        CheckConstraint(_in("match_type", MATCH_TYPES), name="match_type"),
        CheckConstraint(
            "set_person IS NULL OR set_person IN ('Hernan', 'Lauren', 'Joint')", name="set_person"
        ),
        {"schema": "core"},
    )

    rule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(Unicode(200))
    match_type: Mapped[str] = mapped_column(Unicode(12), default="contains")
    category_id: Mapped[int] = mapped_column(ForeignKey("core.category.category_id"))
    # Lower runs first; the first matching active rule wins.
    priority: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Optional range on the absolute amount (F9): the same description can mean two bills
    # ("PAGO IESS" is the empleada's IESS under 300 and the BIESS house loan above).
    amount_min: Mapped[Decimal | None] = mapped_column(Money)
    amount_max: Mapped[Decimal | None] = mapped_column(Money)
    # What else a match does (ADR-042): whose line it is, and the merchant's name.
    set_person: Mapped[str | None] = mapped_column(Unicode(10))
    merchant_name: Mapped[str | None] = mapped_column(Unicode(100))

    category: Mapped[Category] = relationship()


# ---------------- F2: raw workbook, transactions, budget, balances, audit ----------------
class ExcelImport(Base):
    """One loaded Cash Flow workbook. The file itself is not stored, only its hash."""

    __tablename__ = "excel_import"
    __table_args__ = (UniqueConstraint("file_sha256"), {"schema": "raw"})

    import_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_sha256: Mapped[str] = mapped_column(Unicode(64))
    file_name: Mapped[str] = mapped_column(Unicode(260))
    loaded_by: Mapped[str] = mapped_column(Unicode(320))
    loaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExcelCell(Base):
    """Every numeric cell read from the workbook, exactly as read; never edited."""

    __tablename__ = "excel_cell"
    __table_args__ = ({"schema": "raw"},)

    cell_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("raw.excel_import.import_id"))
    sheet: Mapped[str] = mapped_column(Unicode(60))
    cell: Mapped[str] = mapped_column(Unicode(10))
    block: Mapped[str] = mapped_column(Unicode(30))
    group_label: Mapped[str | None] = mapped_column(Unicode(100))
    row_label: Mapped[str] = mapped_column(Unicode(100))
    month: Mapped[date | None] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Money)


class Transaction(Timestamps, Base):
    """Approved money movements. Signed amounts: negative = outflow. USD only."""

    __tablename__ = "transaction"
    __table_args__ = (
        CheckConstraint(_in("type", TXN_TYPES), name="type"),
        CheckConstraint(_in("source", TXN_SOURCES), name="source"),
        CheckConstraint(_in("status", TXN_STATUSES), name="status"),
        CheckConstraint(_in("category_source", CATEGORY_SOURCES), name="category_source"),
        UniqueConstraint("natural_key"),
        {"schema": "core"},
    )

    transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    natural_key: Mapped[str] = mapped_column(Unicode(64))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("core.account.account_id"))
    excel_cell_id: Mapped[int | None] = mapped_column(ForeignKey("raw.excel_cell.cell_id"))
    statement_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw.statement_file.statement_file_id")
    )
    raw_line_id: Mapped[int | None] = mapped_column(ForeignKey("raw.raw_line.raw_line_id"))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("stg.import_batch.batch_id"))
    txn_date: Mapped[date] = mapped_column(Date)
    post_date: Mapped[date | None] = mapped_column(Date)
    # First day of the month the money moved (cash basis); set by the loader from txn_date.
    cash_month: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    description_raw: Mapped[str] = mapped_column(Unicode(400))
    merchant: Mapped[str | None] = mapped_column(Unicode(200))
    pay_reference: Mapped[str | None] = mapped_column(Unicode(100))
    notes: Mapped[str | None] = mapped_column(Unicode(1000))
    type: Mapped[str] = mapped_column(Unicode(12))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))
    person: Mapped[str | None] = mapped_column(Unicode(10))
    country: Mapped[str | None] = mapped_column(Unicode(2))
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    source: Mapped[str] = mapped_column(Unicode(15))
    status: Mapped[str] = mapped_column(Unicode(10), default="confirmed")
    # F9: splits, and where the category came from.
    parent_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.transaction.transaction_id"), index=True
    )
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.merchant_rule.rule_id", ondelete="SET NULL")
    )
    category_source: Mapped[str | None] = mapped_column(Unicode(12))
    # F10: both legs of a transfer between own accounts share this id (the smaller transaction id).
    transfer_group_id: Mapped[int | None] = mapped_column(Integer, index=True)
    # F11: the recurring entry (template x month) this line pays or receives.
    recurring_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.recurring_entry.entry_id", ondelete="SET NULL"), index=True
    )
    # Whose money this is or who it was for (ADR-023): Rubén's money passing through, a loan.
    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.counterparty.counterparty_id", ondelete="SET NULL"), index=True
    )


# ---------------- F11: recurring templates, their amounts and month entries ----------------
class RecurringTemplate(Timestamps, Base):
    """A row that repeats every month (salary, rent, condo fee...). Statement lines are matched to
    it by category, plus the account and description pattern when set, within a tolerance."""

    __tablename__ = "recurring_template"
    __table_args__ = (
        CheckConstraint(_in("type", TXN_TYPES), name="type"),
        CheckConstraint(_in("source", RECURRING_SOURCES), name="source"),
        CheckConstraint("every_months IN (0, 1, 2, 3, 4, 6, 12)", name="every_months"),
        CheckConstraint("due_day IS NULL OR (due_day >= 1 AND due_day <= 31)", name="due_day"),
        UniqueConstraint("name"),
        {"schema": "core"},
    )

    template_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    category_id: Mapped[int] = mapped_column(ForeignKey("core.category.category_id"))
    type: Mapped[str] = mapped_column(Unicode(12))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("core.account.account_id"))
    person: Mapped[str | None] = mapped_column(Unicode(10))
    match_pattern: Mapped[str | None] = mapped_column(Unicode(200))
    tolerance_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2, asdecimal=True), default=Decimal(10), server_default="10"
    )
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    source: Mapped[str] = mapped_column(Unicode(10), default="manual")
    # The workbook row it came from, so Excel history months link to their exact cell.
    excel_block: Mapped[str | None] = mapped_column(Unicode(30))
    excel_group: Mapped[str | None] = mapped_column(Unicode(100))
    excel_label: Mapped[str | None] = mapped_column(Unicode(100))
    notes: Mapped[str | None] = mapped_column(Unicode(400))
    # How often it repeats (ADR-031): 1 monthly, 2, 3, 4, 6 or 12 months; 0 once.
    every_months: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # The day of the month it's usually paid; empty = read from the lines it matched.
    due_day: Mapped[int | None] = mapped_column(Integer)


class RecurringAmount(Base):
    """The template's amount from a month on (signed); "change from month X" adds a row."""

    __tablename__ = "recurring_amount"
    __table_args__ = (UniqueConstraint("template_id", "from_month"), {"schema": "core"})

    amount_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("core.recurring_template.template_id", ondelete="CASCADE")
    )
    from_month: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)


class RecurringEntry(Timestamps, Base):
    """One template in one month: the expected amount. Matched lines point to it."""

    __tablename__ = "recurring_entry"
    __table_args__ = (
        CheckConstraint(_in("status", ENTRY_STATUSES), name="status"),
        UniqueConstraint("template_id", "month"),
        {"schema": "core"},
    )

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("core.recurring_template.template_id", ondelete="CASCADE")
    )
    month: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    # True when this month's amount was set by hand (or copied): template changes leave it alone.
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    status: Mapped[str] = mapped_column(Unicode(8), default="planned", server_default="planned")
    notes: Mapped[str | None] = mapped_column(Unicode(400))


class Budget(Timestamps, Base):
    """Planned amounts per month and category (signed like transactions)."""

    __tablename__ = "budget"
    __table_args__ = (
        UniqueConstraint("month", "category_id", "label", "source"),
        {"schema": "core"},
    )

    budget_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[date] = mapped_column(Date)
    category_id: Mapped[int] = mapped_column(ForeignKey("core.category.category_id"))
    label: Mapped[str] = mapped_column(Unicode(100))
    type: Mapped[str] = mapped_column(Unicode(12))
    amount: Mapped[Decimal] = mapped_column(Money)
    source: Mapped[str] = mapped_column(Unicode(20))


class BalanceSnapshot(Timestamps, Base):
    """A balance at a date: what an account, investment or debt stood at."""

    __tablename__ = "balance_snapshot"
    __table_args__ = (
        CheckConstraint(_in("kind", SNAPSHOT_KINDS), name="kind"),
        UniqueConstraint("as_of", "name", "source"),
        {"schema": "core"},
    )

    snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(Unicode(100))
    kind: Mapped[str] = mapped_column(Unicode(10))
    amount: Mapped[Decimal] = mapped_column(Money)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("core.account.account_id"))
    source: Mapped[str] = mapped_column(Unicode(20))
    notes: Mapped[str | None] = mapped_column(Unicode(400))
    # F14: the holding this balance is a value of (ADR-012).
    holding_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.holding.holding_id", ondelete="CASCADE"), index=True
    )


class Holding(Timestamps, Base):
    """Something the household owns or owes, valued by its balance snapshots (F14, ADR-012).
    Bank accounts and cards are valued from their statements and need no holding."""

    __tablename__ = "holding"
    __table_args__ = (
        CheckConstraint(_in("side", SNAPSHOT_KINDS), name="side"),
        CheckConstraint(_in("holding_class", HOLDING_CLASSES), name="holding_class"),
        UniqueConstraint("name"),
        {"schema": "core"},
    )

    holding_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    side: Mapped[str] = mapped_column(Unicode(10))
    holding_class: Mapped[str] = mapped_column(Unicode(15))
    # A purchase in progress: the amount to pay (the down payment), each installment, the full
    # price, and the category whose lines count as payments.
    target_amount: Mapped[Decimal | None] = mapped_column(Money)
    installment: Mapped[Decimal | None] = mapped_column(Money)
    full_price: Mapped[Decimal | None] = mapped_column(Money)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))
    # A loan's monthly payment (F11 recurring template).
    recurring_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.recurring_template.template_id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Unicode(400))


class Counterparty(Timestamps, Base):
    """Someone money moves to or from (ADR-023): Rubén, whose payments pass through the
    household's accounts. Statement lines whose description contains one of his patterns, and
    transfer notes about him, get his name and his category. With a balance item, the money still
    held for him (or owed by him) shows on Debt & Net Worth."""

    __tablename__ = "counterparty"
    __table_args__ = (UniqueConstraint("name"), {"schema": "core"})

    counterparty_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    # Texts to find in statement descriptions, separated by ";" ("RUBEN MIRANDA; NAPOLES").
    patterns: Mapped[str | None] = mapped_column(Unicode(400))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))
    # The personal_loan item on Debt & Net Worth his lines move: its latest value plus them.
    holding_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.holding.holding_id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Unicode(400))


class UserSetting(Base):
    """One signed-in person's choice (ADR-026): the Both/Hernan/Lauren switch, a table's columns
    and row size, saved views, Home widgets. The value is JSON the web app owns; nothing here is
    financial, and each person only reads and writes their own."""

    __tablename__ = "user_setting"
    __table_args__ = ({"schema": "core"},)

    user_email: Mapped[str] = mapped_column(Unicode(254), primary_key=True)
    key: Mapped[str] = mapped_column(Unicode(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(UnicodeText)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class TransferNote(Timestamps, Base):
    """A transfer told to the app before (or after) its statement (ADR-023): the statement says
    "TRANSFERENCIA", the note says who and why. Matched to the line with the same signed amount,
    in the note's account when it has one, at most 5 days apart."""

    __tablename__ = "transfer_note"
    __table_args__ = (
        CheckConstraint(_in("source", NOTE_SOURCES), name="source"),
        {"schema": "core"},
    )

    note_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)  # signed: negative = sent
    account_id: Mapped[int | None] = mapped_column(ForeignKey("core.account.account_id"))
    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.counterparty.counterparty_id")
    )
    category_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))
    other_party: Mapped[str | None] = mapped_column(Unicode(100))  # the name the bank printed
    # The person's part of a shared payment (positive): the matched line is split into this, in
    # the person's category, and the rest, in the note's category.
    share: Mapped[Decimal | None] = mapped_column(Money)
    description: Mapped[str | None] = mapped_column(Unicode(400))
    source: Mapped[str] = mapped_column(Unicode(10), default="manual")
    # The bank's reference, so the same email read twice makes one note.
    reference: Mapped[str | None] = mapped_column(Unicode(64), index=True)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.transaction.transaction_id"), index=True
    )
    created_by: Mapped[str] = mapped_column(Unicode(320))


class LoanInstallment(Base):
    """One installment of a loan's amortization table (F14, ADR-014): what it pays and the
    balance after it. Only numbers are kept; the lender's file is not stored."""

    __tablename__ = "loan_installment"
    __table_args__ = (
        CheckConstraint(_in("status", ("paid", "due")), name="status"),
        UniqueConstraint("holding_id", "number"),
        {"schema": "core"},
    )

    installment_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holding_id: Mapped[int] = mapped_column(
        ForeignKey("core.holding.holding_id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    period: Mapped[date] = mapped_column(Date)  # first day of the month it is due
    principal: Mapped[Decimal] = mapped_column(Money)
    interest: Mapped[Decimal] = mapped_column(Money)
    other: Mapped[Decimal] = mapped_column(Money)  # insurance, late interest, other charges
    total: Mapped[Decimal] = mapped_column(Money)
    balance_after: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(Unicode(4))


class InvestmentPosition(Base):
    """One position of an investment account on a day (F22, ADR-019): read from the broker's
    report (Interactive Brokers Flex), replaced when the same day is read again."""

    __tablename__ = "investment_position"
    __table_args__ = (
        UniqueConstraint("holding_id", "as_of", "symbol", "asset_class"),
        {"schema": "core"},
    )

    position_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holding_id: Mapped[int] = mapped_column(
        ForeignKey("core.holding.holding_id", ondelete="CASCADE"), index=True
    )
    as_of: Mapped[date] = mapped_column(Date)
    symbol: Mapped[str] = mapped_column(Unicode(40))
    description: Mapped[str | None] = mapped_column(Unicode(200))
    asset_class: Mapped[str] = mapped_column(Unicode(20))
    currency: Mapped[str] = mapped_column(Unicode(3))
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 6))
    price: Mapped[Decimal] = mapped_column(Numeric(19, 6))
    value: Mapped[Decimal] = mapped_column(Money)  # in USD
    cost_basis: Mapped[Decimal | None] = mapped_column(Money)
    unrealized: Mapped[Decimal | None] = mapped_column(Money)


PRODUCT_GROUPS = (
    "Meat & Fish",
    "Dairy & Eggs",
    "Fruit & Vegetables",
    "Bakery",
    "Pantry",
    "Snacks & Sweets",
    "Drinks",
    "Alcohol",
    "Frozen & Ready Meals",
    "Baby",
    "Household & Cleaning",
    "Personal Care",
    "Health & Pharmacy",
    "Pets",
    "Services",
    "Car",
    "Other",
)
GROUP_SOURCES = ("rule", "keyword", "claude", "confirmed")
LABEL_SOURCES = ("claude", "confirmed")  # who set a purchase item's type and brand (ADR-061)
# SRI's six categories of deductible personal expenses (ADR-036)
GP_CATEGORIES = ("vivienda", "educacion", "salud", "alimentacion", "vestimenta", "turismo")


class Invoice(Base):
    """An electronic invoice (SRI "factura") received by email or uploaded (F21, ADR-021): who
    issued it, when, its totals, and the card or bank line it was paid with once matched. The
    buyer's identification isn't stored."""

    __tablename__ = "invoice"
    __table_args__ = (
        CheckConstraint(
            f"gp_category IS NULL OR gp_category = 'none' OR {_in('gp_category', GP_CATEGORIES)}",
            name="gp_category",
        ),
        {"schema": "core"},
    )

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_key: Mapped[str] = mapped_column(Unicode(49), unique=True)  # SRI's clave de acceso
    issuer_ruc: Mapped[str] = mapped_column(Unicode(13))
    issuer_name: Mapped[str] = mapped_column(Unicode(300))
    number: Mapped[str] = mapped_column(Unicode(20))  # 072-140-000340106
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    subtotal: Mapped[Decimal] = mapped_column(Money)
    tax: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("core.transaction.transaction_id", ondelete="SET NULL"), index=True
    )
    received_by: Mapped[str] = mapped_column(Unicode(320))
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Gastos personales (ADR-036): whose invoice (never the buyer's ID) and a chosen category.
    person: Mapped[str | None] = mapped_column(Unicode(20))
    gp_category: Mapped[str | None] = mapped_column(Unicode(20))
    # The app category chosen for it (ADR-045); gp_category then follows from it.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.line_no"
    )


class InvoiceLine(Base):
    """One product on an invoice, with the product group it was put in."""

    __tablename__ = "invoice_line"
    __table_args__ = (
        CheckConstraint(
            f"product_group IS NULL OR {_in('product_group', PRODUCT_GROUPS)}", name="group"
        ),
        CheckConstraint(
            f"group_source IS NULL OR {_in('group_source', GROUP_SOURCES)}", name="source"
        ),
        CheckConstraint(
            f"label_source IS NULL OR {_in('label_source', LABEL_SOURCES)}", name="label_source"
        ),
        {"schema": "core"},
    )

    line_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("core.invoice.invoice_id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer)
    code: Mapped[str | None] = mapped_column(Unicode(60))
    description: Mapped[str] = mapped_column(Unicode(300))
    product_key: Mapped[str] = mapped_column(Unicode(300), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 6))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 6))
    discount: Mapped[Decimal] = mapped_column(Money)
    subtotal: Mapped[Decimal] = mapped_column(Money)  # before tax, after discount
    tax: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)  # what was paid for this line
    product_group: Mapped[str | None] = mapped_column(Unicode(40))
    group_source: Mapped[str | None] = mapped_column(Unicode(10))
    # The app category of this item (ADR-050): the same list as everywhere else.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))
    # What it is and who makes it (ADR-061): "Cheese", "Kiosko"; set by Claude or confirmed.
    product_type: Mapped[str | None] = mapped_column(Unicode(60))
    brand: Mapped[str | None] = mapped_column(Unicode(60))
    label_source: Mapped[str | None] = mapped_column(Unicode(10))

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class ProductRule(Base):
    """A product's group, confirmed once by a person (or Claude's suggestion, accepted): every
    invoice line with the same product key gets it."""

    __tablename__ = "product_rule"
    __table_args__ = (
        CheckConstraint(_in("product_group", PRODUCT_GROUPS), name="group"),
        {"schema": "core"},
    )

    rule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_key: Mapped[str] = mapped_column(Unicode(300), unique=True)
    product_group: Mapped[str | None] = mapped_column(Unicode(40))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))
    product_type: Mapped[str | None] = mapped_column(Unicode(60))
    brand: Mapped[str | None] = mapped_column(Unicode(60))
    created_by: Mapped[str] = mapped_column(Unicode(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppSetting(Base):
    """A household-wide setting (F19, ADR-018), e.g. statements_from: the first month whose
    statements count instead of the Cash Flow workbook (YYYY-MM-01)."""

    __tablename__ = "app_setting"
    __table_args__ = ({"schema": "core"},)

    setting_key: Mapped[str] = mapped_column(Unicode(50), primary_key=True)
    setting_value: Mapped[str] = mapped_column(Unicode(200))
    updated_by: Mapped[str] = mapped_column(Unicode(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MonthlyReport(Base):
    """One month's report (F16, ADR-015): the facts worked out from the data and the 3 to 5
    findings written from them, by Claude or by rules. Regenerating replaces it."""

    __tablename__ = "monthly_report"
    __table_args__ = (
        UniqueConstraint("month"),
        CheckConstraint(_in("written_by", ("claude", "rules")), name="written_by"),
        {"schema": "core"},
    )

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[date] = mapped_column(Date)
    written_by: Mapped[str] = mapped_column(Unicode(6))
    model: Mapped[str | None] = mapped_column(Unicode(60))
    facts_json: Mapped[str] = mapped_column(UnicodeText)
    findings_json: Mapped[str] = mapped_column(UnicodeText)
    generated_by: Mapped[str] = mapped_column(Unicode(200))
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LoadLog(Base):
    __tablename__ = "load_log"
    __table_args__ = ({"schema": "audit"},)

    load_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(Unicode(30))
    file_sha256: Mapped[str | None] = mapped_column(Unicode(64))
    loaded_by: Mapped[str] = mapped_column(Unicode(320))
    loaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    rows_loaded: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(UnicodeText)


class ChangeLog(Base):
    """Every edit to a loaded line (F9): who changed which column, from what to what."""

    __tablename__ = "change_log"
    __table_args__ = ({"schema": "audit"},)

    change_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_name: Mapped[str] = mapped_column(Unicode(60))
    row_id: Mapped[int] = mapped_column(Integer, index=True)
    column_name: Mapped[str] = mapped_column(Unicode(60))
    old_value: Mapped[str | None] = mapped_column(Unicode(400))
    new_value: Mapped[str | None] = mapped_column(Unicode(400))
    reason: Mapped[str] = mapped_column(Unicode(200))
    changed_by: Mapped[str] = mapped_column(Unicode(320))
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MerchantSuggestion(Base):
    """Claude's category suggestion for a merchant nobody has categorized yet (F9)."""

    __tablename__ = "merchant_suggestion"
    __table_args__ = (UniqueConstraint("merchant_key"), {"schema": "core"})

    suggestion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_key: Mapped[str] = mapped_column(Unicode(200))
    category_id: Mapped[int] = mapped_column(
        ForeignKey("core.category.category_id", ondelete="CASCADE")
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    reason: Mapped[str] = mapped_column(Unicode(400))
    model: Mapped[str] = mapped_column(Unicode(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------- F3: uploaded statements ----------------
class StatementFile(Base):
    """One uploaded statement PDF. The file is in blob storage; only metadata is here."""

    __tablename__ = "statement_file"
    __table_args__ = (
        CheckConstraint(_in("source", STATEMENT_SOURCES), name="source"),
        CheckConstraint(_in("status", STATEMENT_STATUSES), name="status"),
        UniqueConstraint("sha256"),
        {"schema": "raw"},
    )

    statement_file_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(Unicode(64))
    file_name: Mapped[str] = mapped_column(Unicode(260))
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Unicode(12))
    status: Mapped[str] = mapped_column(Unicode(15))
    # Last four digits found in the file, comma-separated ("8872,1862"); never full numbers.
    last4_found: Mapped[str | None] = mapped_column(Unicode(60))
    account_match: Mapped[str | None] = mapped_column(Unicode(10))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    blob_key: Mapped[str] = mapped_column(Unicode(200))
    uploaded_by: Mapped[str] = mapped_column(Unicode(320))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    accounts: Mapped[list["Account"]] = relationship(
        secondary="raw.statement_file_account", order_by="Account.name"
    )


class StatementFileAccount(Base):
    """Accounts a statement covers (a BofA combined statement covers checking and savings)."""

    __tablename__ = "statement_file_account"
    __table_args__ = ({"schema": "raw"},)

    statement_file_id: Mapped[int] = mapped_column(
        ForeignKey("raw.statement_file.statement_file_id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("core.account.account_id"), primary_key=True)


# ---------------- F4: parsed statements, staging, rejects ----------------
class StatementHeader(Base):
    """What a parser read from a statement's summary: period, balances and section totals."""

    __tablename__ = "statement_header"
    __table_args__ = ({"schema": "raw"},)

    statement_file_id: Mapped[int] = mapped_column(
        ForeignKey("raw.statement_file.statement_file_id", ondelete="CASCADE"), primary_key=True
    )
    parser: Mapped[str] = mapped_column(Unicode(30))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    opening_balance: Mapped[Decimal | None] = mapped_column(Money)
    closing_balance: Mapped[Decimal | None] = mapped_column(Money)
    # Section totals as printed, e.g. {"payments": "4000.00", "transactions": "3932.84"} (JSON).
    totals_json: Mapped[str] = mapped_column(UnicodeText)
    parsed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RawLine(Base):
    """One statement line exactly as read (text plus the fields the parser took from it)."""

    __tablename__ = "raw_line"
    __table_args__ = ({"schema": "raw"},)

    raw_line_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_file_id: Mapped[int] = mapped_column(
        ForeignKey("raw.statement_file.statement_file_id", ondelete="CASCADE"), index=True
    )
    page: Mapped[int] = mapped_column(Integer)
    line_no: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(Unicode(30))
    cardholder: Mapped[str | None] = mapped_column(Unicode(10))
    text: Mapped[str] = mapped_column(Unicode(400))
    data_json: Mapped[str] = mapped_column(UnicodeText)


class ImportBatch(Base):
    """One statement's lines waiting in staging for Hernan's approval."""

    __tablename__ = "import_batch"
    __table_args__ = (
        CheckConstraint(_in("status", BATCH_STATUSES), name="status"),
        {"schema": "stg"},
    )

    batch_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_file_id: Mapped[int] = mapped_column(
        ForeignKey("raw.statement_file.statement_file_id"), index=True
    )
    status: Mapped[str] = mapped_column(Unicode(10), default="preview")
    tieout_ok: Mapped[bool] = mapped_column(Boolean)
    # The checks shown in the preview: [{"name", "expected", "actual", "ok"}] (JSON).
    checks_json: Mapped[str] = mapped_column(UnicodeText)
    created_by: Mapped[str] = mapped_column(Unicode(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_by: Mapped[str | None] = mapped_column(Unicode(320))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)


class StgTransaction(Base):
    __tablename__ = "stg_transaction"
    __table_args__ = ({"schema": "stg"},)

    stg_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("stg.import_batch.batch_id", ondelete="CASCADE"), index=True
    )
    raw_line_id: Mapped[int] = mapped_column(ForeignKey("raw.raw_line.raw_line_id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("core.account.account_id"))
    natural_key: Mapped[str] = mapped_column(Unicode(64))
    txn_date: Mapped[date] = mapped_column(Date)
    post_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    description_raw: Mapped[str] = mapped_column(Unicode(400))
    merchant: Mapped[str | None] = mapped_column(Unicode(200))
    type: Mapped[str] = mapped_column(Unicode(12))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("core.category.category_id"))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("core.merchant_rule.rule_id"))
    # Set when a person chose the category on the statement's page (F23): "manual" or
    # "suggestion". Otherwise approval derives it (rule or the statement's section).
    category_source: Mapped[str | None] = mapped_column(Unicode(12))
    person: Mapped[str | None] = mapped_column(Unicode(10))
    country: Mapped[str | None] = mapped_column(Unicode(2))
    pay_reference: Mapped[str | None] = mapped_column(Unicode(100))
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)


class RejectedLine(Base):
    """A line that looked like a transaction but could not be read or placed."""

    __tablename__ = "rejected_line"
    __table_args__ = ({"schema": "rej"},)

    rejected_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_file_id: Mapped[int] = mapped_column(
        ForeignKey("raw.statement_file.statement_file_id", ondelete="CASCADE"), index=True
    )
    page: Mapped[int] = mapped_column(Integer)
    line_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Unicode(400))
    reason: Mapped[str] = mapped_column(Unicode(200))


# ---------------- mart views (read-only; created by migrations from sql/views) ----------------
mart = MetaData()

v_monthly_cashflow = Table(
    "v_monthly_cashflow",
    mart,
    Column("cash_month", Date, primary_key=True),
    Column("income", Money),
    Column("expenses", Money),
    Column("savings", Money),
    Column("debt_payments", Money),
    Column("net", Money),
    Column("cumulative_net", Money),
    Column("savings_rate", Numeric(9, 4)),
    Column("transactions", Integer),
    schema="mart",
)

v_monthly_cash = Table(
    "v_monthly_cash",
    mart,
    Column("cash_month", Date, primary_key=True),
    Column("income", Money),
    Column("expenses", Money),
    Column("card_payments", Money),
    Column("savings", Money),
    Column("debt_payments", Money),
    Column("net", Money),
    Column("cumulative_net", Money),
    Column("savings_rate", Numeric(9, 4)),
    Column("transactions", Integer),
    schema="mart",
)

v_category_month = Table(
    "v_category_month",
    mart,
    Column("cash_month", Date, primary_key=True),
    Column("type", Unicode(12), primary_key=True),
    Column("group_id", Integer, primary_key=True),
    Column("group_name", Unicode(100)),
    Column("group_color", Unicode(7)),
    Column("category_id", Integer, primary_key=True),
    Column("category_name", Unicode(100)),
    Column("amount", Money),
    Column("transactions", Integer),
    schema="mart",
)

v_spending_line = Table(
    "v_spending_line",
    mart,
    Column("transaction_id", Integer, primary_key=True),
    Column("cash_month", Date),
    Column("txn_date", Date),
    Column("source", Unicode(15)),
    Column("type", Unicode(12)),
    Column("amount", Money),
    Column("group_id", Integer),
    Column("group_name", Unicode(100)),
    Column("group_color", Unicode(7)),
    Column("category_id", Integer),
    Column("category_name", Unicode(100)),
    Column("person", Unicode(10)),
    Column("country", Unicode(2)),
    Column("is_fixed", Boolean),
    Column("merchant", Unicode(400)),
    Column("description", Unicode(400)),
    Column("account_id", Integer),
    Column("account_name", Unicode(100)),
    schema="mart",
)

v_excel_month = Table(
    "v_excel_month",
    mart,
    Column("cash_month", Date, primary_key=True),
    schema="mart",
)

v_debt_cost = Table(
    "v_debt_cost",
    mart,
    Column("cash_month", Date, primary_key=True),
    Column("account_id", Integer, primary_key=True),
    Column("account_name", Unicode(100)),
    Column("account_kind", Unicode(20)),
    Column("kind", Unicode(8), primary_key=True),
    Column("category_name", Unicode(100), primary_key=True),
    Column("amount", Money),
    Column("transactions", Integer),
    schema="mart",
)


class GpIssuerRule(Base):
    """An issuer's SRI category for gastos personales, saved from a person's choice (ADR-036);
    'none' = this issuer's invoices aren't deductible."""

    __tablename__ = "gp_issuer_rule"
    __table_args__ = (
        CheckConstraint(
            f"gp_category = 'none' OR {_in('gp_category', GP_CATEGORIES)}", name="category"
        ),
        {"schema": "core"},
    )

    gp_issuer_rule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issuer_ruc: Mapped[str] = mapped_column(Unicode(13), unique=True)
    gp_category: Mapped[str] = mapped_column(Unicode(20))
    created_by: Mapped[str] = mapped_column(Unicode(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


IVA_USES = ("business", "personal", "none")  # a received invoice in the IVA return (ADR-062)


class SaleInvoice(Base):
    """An invoice the household issued (Hernan's work invoices), for the monthly IVA return
    (ADR-062). Kept apart from core.invoice, which holds what was bought."""

    __tablename__ = "sale_invoice"
    __table_args__ = ({"schema": "core"},)

    sale_invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_key: Mapped[str] = mapped_column(Unicode(49), unique=True)
    person: Mapped[str] = mapped_column(Unicode(20))  # who issued it
    number: Mapped[str] = mapped_column(Unicode(20))
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    buyer_name: Mapped[str] = mapped_column(Unicode(300))
    base_taxed: Mapped[Decimal] = mapped_column(Money)  # subject to IVA above 0%
    base_zero: Mapped[Decimal] = mapped_column(Money)  # 0% or exempt
    tax: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)
    received_by: Mapped[str] = mapped_column(Unicode(320))
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Withholding(Base):
    """A comprobante de retención a client issued to the household: income tax and IVA it kept
    back from an invoice (ADR-062)."""

    __tablename__ = "withholding"
    __table_args__ = ({"schema": "core"},)

    withholding_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_key: Mapped[str] = mapped_column(Unicode(49), unique=True)
    person: Mapped[str] = mapped_column(Unicode(20))  # whose income it was kept from
    issuer_ruc: Mapped[str] = mapped_column(Unicode(13))
    issuer_name: Mapped[str] = mapped_column(Unicode(300))
    number: Mapped[str] = mapped_column(Unicode(20))
    issue_date: Mapped[date] = mapped_column(Date)
    period: Mapped[date] = mapped_column(Date, index=True)  # periodo fiscal, first of the month
    invoice_number: Mapped[str | None] = mapped_column(Unicode(20))  # the sale it withholds on
    income_tax: Mapped[Decimal] = mapped_column(Money)
    iva: Mapped[Decimal] = mapped_column(Money)
    received_by: Mapped[str] = mapped_column(Unicode(320))
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TaxNote(Base):
    """A nota de crédito or nota de débito, issued by the household or received, for the IVA
    return (ADR-064): it lowers (crédito) or raises (débito) the sales or purchases of its month."""

    __tablename__ = "tax_note"
    __table_args__ = (
        CheckConstraint("kind IN ('credit', 'debit')", name="kind"),
        CheckConstraint("direction IN ('issued', 'received')", name="direction"),
        {"schema": "core"},
    )

    tax_note_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_key: Mapped[str] = mapped_column(Unicode(49), unique=True)
    kind: Mapped[str] = mapped_column(Unicode(10))
    direction: Mapped[str] = mapped_column(Unicode(10))
    person: Mapped[str] = mapped_column(Unicode(20))
    issuer_ruc: Mapped[str] = mapped_column(Unicode(13))
    issuer_name: Mapped[str] = mapped_column(Unicode(300))
    counterpart_name: Mapped[str] = mapped_column(Unicode(300))  # the buyer of an issued note
    number: Mapped[str] = mapped_column(Unicode(20))
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    modified_number: Mapped[str | None] = mapped_column(Unicode(20))  # the invoice it changes
    reason: Mapped[str | None] = mapped_column(Unicode(300))
    base_taxed: Mapped[Decimal] = mapped_column(Money)
    base_zero: Mapped[Decimal] = mapped_column(Money)
    tax: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)
    received_by: Mapped[str] = mapped_column(Unicode(320))
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TaxIssuerRule(Base):
    """How an issuer's invoices count in the IVA return: a business purchase (IVA credit), a
    personal expense, or neither (ADR-062)."""

    __tablename__ = "tax_issuer_rule"
    __table_args__ = (
        CheckConstraint(_in("iva_use", IVA_USES), name="iva_use"),
        {"schema": "core"},
    )

    tax_issuer_rule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issuer_ruc: Mapped[str] = mapped_column(Unicode(13), unique=True)
    iva_use: Mapped[str] = mapped_column(Unicode(10))
    created_by: Mapped[str] = mapped_column(Unicode(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GpProfile(Base):
    """A person's cargas familiares for a tax year, which set the cap (ADR-036)."""

    __tablename__ = "gp_profile"
    __table_args__ = (
        CheckConstraint("cargas >= 0 AND cargas <= 20", name="cargas"),
        {"schema": "core"},
    )

    person: Mapped[str] = mapped_column(Unicode(20), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    cargas: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    catastrophic: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class BudgetPlan(Base):
    """A spending group's monthly budget from a month on (ADR-039); the latest start on or before
    a month sets it. Amount 0 = no budget from then; rollover carries what's left (or overspent)
    into the next month."""

    __tablename__ = "budget_plan"
    __table_args__ = (
        UniqueConstraint("category_id", "start_month"),
        CheckConstraint("amount >= 0", name="amount"),
        {"schema": "core"},
    )

    budget_plan_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("core.category.category_id"))
    start_month: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    rollover: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_by: Mapped[str] = mapped_column(Unicode(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Goal(Base):
    """A saving goal (ADR-040): reach target_amount (by target_date), with the money in a bank
    account or balance-sheet item (item_key, "account-12" or "holding-5") or, without one, the
    amount saved typed by hand; monthly_amount is what's planned to go in each month."""

    __tablename__ = "goal"
    __table_args__ = (CheckConstraint("target_amount > 0", name="target"), {"schema": "core"})

    goal_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(100))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    target_date: Mapped[date | None] = mapped_column(Date)
    item_key: Mapped[str | None] = mapped_column(Unicode(40))
    saved_amount: Mapped[Decimal | None] = mapped_column(Money)
    monthly_amount: Mapped[Decimal | None] = mapped_column(Money)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Unicode(400))
    created_by: Mapped[str] = mapped_column(Unicode(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


@event.listens_for(Session, "before_flush")
def _settle_months(session: Session, _context: object, _instances: object) -> None:
    """A salary counts in the month it pays for (ADR-084): every flush sets each new or changed
    line's cash_month. The import is here because the service imports these models."""
    from app.services import payday

    payday.settle(session)
