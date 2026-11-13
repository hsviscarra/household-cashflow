"""Request and response models: reference data (F1), history and cash flow (F2).

Money is Decimal and serializes as a JSON string, so no precision is lost on the way to the UI.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AccountKind = Literal["checking", "savings", "credit_card"]
Owner = Literal["Hernan", "Lauren", "Joint"]
Country = Literal["US", "EC"]
CategoryKind = Literal["income", "expense", "savings", "transfer", "debt"]
MatchType = Literal["contains", "starts_with", "regex"]

HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- accounts ----------
class AccountIn(BaseModel):
    """A new bank account or card."""

    name: str = Field(min_length=1, max_length=100)
    institution: str = Field(min_length=1, max_length=100)
    kind: AccountKind
    owner: Owner
    country: Country
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    is_active: bool = True
    # Closed or suspended on this day: no statements are expected after it (old ones still load).
    closed_on: date | None = None
    opened_on: date | None = None  # opened on this day: no statements expected before it


class AccountPatch(BaseModel):
    """The fields of an account to change."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    institution: str | None = Field(default=None, min_length=1, max_length=100)
    kind: AccountKind | None = None
    owner: Owner | None = None
    country: Country | None = None
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    is_active: bool | None = None
    closed_on: date | None = None
    opened_on: date | None = None


class AccountOut(_Out):
    """An account as the API returns it."""

    account_id: int
    name: str
    institution: str
    kind: AccountKind
    owner: Owner
    country: Country
    last4: str | None
    is_active: bool
    closed_on: date | None = None
    opened_on: date | None = None


# ---------- categories ----------
class CategoryIn(BaseModel):
    """A new group (no parent, needs a kind) or a category under one."""

    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    kind: CategoryKind | None = None  # required for a group; a subcategory takes its parent's
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    is_fixed: bool = False
    description: str | None = Field(default=None, max_length=400)


class CategoryPatch(BaseModel):
    """The fields of a category to change."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    is_fixed: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    description: str | None = Field(default=None, max_length=400)
    # Move a subcategory to another group of the same kind (F23). Its lines and rules follow.
    parent_id: int | None = None


class CategoryOut(_Out):
    """A category as the API returns it."""

    category_id: int
    parent_id: int | None
    name: str
    kind: CategoryKind
    color: str | None
    is_fixed: bool
    is_active: bool
    sort_order: int
    description: str | None = None
    # How often it's used: loaded lines in it and rules pointing at it (the picker lists the
    # most-used first; Settings shows them). Only filled by the categories list.
    lines: int = 0
    rules: int = 0


class CategoryUsesOut(BaseModel):
    """What uses a category, or what moved when it was deleted (ADR-034)."""

    lines: int
    rules: int
    bills: int
    budgets: int
    other: int
    total: int


class CategoryGroup(CategoryOut):
    """A group with the categories under it."""

    children: list[CategoryOut]


# ---------- merchant rules ----------
class RuleIn(BaseModel):
    """A new merchant rule: a pattern, how it matches and the category it gives."""

    pattern: str = Field(min_length=1, max_length=200)
    match_type: MatchType = "contains"
    category_id: int
    priority: int = Field(default=50, ge=0, le=999)
    is_active: bool = True
    amount_min: Decimal | None = Field(default=None, ge=0)
    amount_max: Decimal | None = Field(default=None, ge=0)
    set_person: Literal["Hernan", "Lauren", "Joint"] | None = None
    merchant_name: str | None = Field(default=None, max_length=100)

    @field_validator("pattern")
    @classmethod
    def strip_pattern(cls, v: str) -> str:
        """A rule's pattern never starts or ends with spaces."""
        return v.strip()


class RulePatch(BaseModel):
    """The fields of a merchant rule to change."""

    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    match_type: MatchType | None = None
    category_id: int | None = None
    priority: int | None = Field(default=None, ge=0, le=999)
    is_active: bool | None = None
    amount_min: Decimal | None = Field(default=None, ge=0)
    amount_max: Decimal | None = Field(default=None, ge=0)
    set_person: Literal["Hernan", "Lauren", "Joint"] | None = None
    merchant_name: str | None = Field(default=None, max_length=100)


class RuleOut(_Out):
    """A merchant rule with its category's full name."""

    rule_id: int
    pattern: str
    match_type: MatchType
    category_id: int
    category_path: str
    priority: int
    is_active: bool
    amount_min: Decimal | None
    amount_max: Decimal | None
    set_person: str | None = None
    merchant_name: str | None = None
    # Lines this save categorized (loaded or waiting for approval); 0 when only listing.
    applied: int = 0


class RuleTestOut(BaseModel):
    """What a description would match: the rule, or none."""

    description: str
    rule: RuleOut | None


# ---------------- F2: Excel history and cash flow ----------------
class MonthCheckOut(BaseModel):
    """One workbook month checked: what the rows add up to against the sheet's own totals."""

    month: date
    sheet: str
    income_rows: Decimal
    income_workbook: Decimal | None
    expense_rows: Decimal
    expense_workbook: Decimal | None
    left_out: list[str]
    typed_total: bool
    explained: bool


class MappingReviewOut(BaseModel):
    """How one workbook row is read: its type, category and person, and the months it has."""

    block: str
    group: str | None
    label: str
    type: str
    category: str
    person: str | None
    months: int
    total: Decimal
    review: str | None


class SnapshotOut(BaseModel):
    """A balance the workbook records for a day."""

    as_of: date
    name: str
    kind: str
    amount: Decimal
    notes: str


class YearTotalOut(BaseModel):
    """A year of the workbook: months, income and outflows."""

    year: int
    months: int
    income: Decimal
    outflows: Decimal


class UnmappedOut(BaseModel):
    """A workbook row with no category mapping yet."""

    sheet: str
    cell: str
    block: str
    group: str | None
    label: str
    value: Decimal


class HistoryPreviewOut(BaseModel):
    """What loading the workbook would do, before doing it."""

    file_name: str
    file_sha256: str
    already_loaded: bool
    first_month: date | None
    last_month: date | None
    months: int
    actual_rows: int
    plan_rows: int
    plan_months: list[date]
    years: list[YearTotalOut]
    mismatches: list[MonthCheckOut]
    unmapped: list[UnmappedOut]
    mapping: list[MappingReviewOut]
    snapshots: list[SnapshotOut]
    side_cells: int


class HistoryLoadOut(BaseModel):
    """What loading the workbook did."""

    load_id: int
    transactions: int
    budget_rows: int
    snapshots: int
    raw_cells: int
    replaced_transactions: int


class MonthlyCashflowOut(BaseModel):
    """A month of cash flow: income, expenses, savings, debt payments and net."""

    cash_month: date
    income: Decimal
    expenses: Decimal
    card_payments: Decimal = Decimal(0)  # cash view only: bank-to-card payments (F10)
    savings: Decimal
    debt_payments: Decimal
    net: Decimal
    cumulative_net: Decimal
    savings_rate: Decimal | None
    transactions: int


class CategoryMonthOut(BaseModel):
    """One category's amount in one month."""

    cash_month: date
    type: str
    group_id: int
    group_name: str
    group_color: str | None
    category_id: int
    category_name: str
    amount: Decimal
    transactions: int


class PlanMonthOut(BaseModel):
    """A month the workbook planned: income and outflows."""

    month: date
    income: Decimal
    outflows: Decimal


# ---------------- F3: statements ----------------
class BatchRef(BaseModel):
    """A statement's latest batch, briefly."""

    batch_id: int
    status: str
    tieout_ok: bool


class StatementAccountOut(_Out):
    """An account a statement belongs to."""

    account_id: int
    name: str
    last4: str | None


class StatementOut(_Out):
    """A stored statement with its accounts and latest batch."""

    statement_file_id: int
    file_name: str
    source: str
    source_label: str
    status: str
    accounts: list[StatementAccountOut]
    account_match: str | None
    last4_found: list[str]
    period_start: date | None
    period_end: date | None
    page_count: int
    size_bytes: int
    uploaded_by: str
    uploaded_at: datetime
    can_read: bool = False
    batch: BatchRef | None = None


class UploadResultOut(BaseModel):
    """What happened to one uploaded file: stored, duplicate or rejected, and why."""

    file_name: str
    outcome: Literal["stored", "duplicate", "rejected"]
    message: str
    statement: StatementOut | None = None


class StatementPatch(BaseModel):
    """The accounts a statement belongs to."""

    account_ids: list[int] = Field(min_length=1, max_length=4)


# ---------------- F4: import batches and transactions ----------------
class CheckOut(BaseModel):
    """One tie-out check: what the statement printed against what the lines add up to."""

    name: str
    expected: Decimal
    actual: Decimal
    ok: bool


class StgLineOut(BaseModel):
    """A line waiting in a batch, with its proposed category and matches."""

    stg_id: int
    txn_date: date
    post_date: date | None
    description: str
    merchant: str | None
    amount: Decimal
    type: str
    category_id: int | None
    category_path: str | None
    person: str | None
    country: str | None
    cardholder: str | None
    account_name: str | None = None
    pay_reference: str | None = None
    is_duplicate: bool
    # What a transfer note or a person will do to the line at approval (ADR-023).
    hint_source: Literal["note", "person"] | None = None
    hint_person: str | None = None
    hint_text: str | None = None
    hint_share: Decimal | None = None


class CategoryTotalOut(BaseModel):
    """What a batch adds to one category."""

    category_path: str
    type: str
    lines: int
    amount: Decimal


class RejectOut(BaseModel):
    """A statement line that couldn't be read, and why."""

    page: int
    line_no: int
    text: str
    reason: str


class BatchOut(BaseModel):
    """A batch as the Import page shows it."""

    batch_id: int
    status: str
    tieout_ok: bool
    statement: StatementOut
    period_start: date
    period_end: date
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    checks: list[CheckOut]
    lines: list[StgLineOut]
    by_category: list[CategoryTotalOut]
    rejects: list[RejectOut]
    new_lines: int
    duplicate_lines: int
    uncategorized: int
    created_by: str
    decided_by: str | None
    decided_at: datetime | None


class ApproveOut(BaseModel):
    """What approving a batch loaded and skipped."""

    batch_id: int
    loaded: int
    skipped_duplicates: int


class LearnedOut(BaseModel):
    """The rule saved because a merchant was categorized the same way twice by hand."""

    rule_id: int
    pattern: str
    lines: int


class TransactionOut(BaseModel):
    """An approved line as the API returns it."""

    transaction_id: int
    txn_date: date
    post_date: date | None
    cash_month: date
    month_override: date | None = None  # set when a person chose the month (ADR-089)
    account_id: int | None
    account_name: str | None
    description: str
    merchant: str | None
    amount: Decimal
    type: str
    category_id: int | None
    category_path: str | None
    person: str | None
    country: str | None
    source: str
    statement_file_id: int | None
    notes: str | None = None
    category_source: str | None = None
    parent_transaction_id: int | None = None
    parts: int = 0  # > 0: split into this many parts, which count instead of this line
    # Set on the answer to an edit that taught the app a rule (ADR-079).
    learned: "LearnedOut | None" = None
    transfer_group_id: int | None = None
    transfer_with: "TransferLegOut | None" = None  # the other side of a matched transfer
    recurring_entry_id: int | None = None  # F11: the recurring entry this line pays
    counterparty_id: int | None = None  # whose money it is or who it was for (ADR-023)


# ---------------- F9: classification ----------------
class SuggestionOut(BaseModel):
    """Claude's suggested category for a merchant, with its confidence and reason."""

    category_id: int
    category_path: str
    confidence: Decimal
    reason: str
    model: str


class ReviewLineOut(BaseModel):
    """A line waiting for a category."""

    transaction_id: int  # on a statement's page (F23), the staged line's id
    txn_date: date
    amount: Decimal
    description: str
    account_name: str | None
    person: str | None
    post_date: date | None = None
    statement_file_id: int | None = None
    page: int | None = None


class ReviewGroupOut(BaseModel):
    """A merchant's waiting lines with their total and any suggestion."""

    merchant_key: str
    lines: list[ReviewLineOut]
    total: Decimal
    suggestion: SuggestionOut | None


class ReviewOut(BaseModel):
    """Everything waiting for a category, grouped by merchant."""

    month: date | None
    groups: list[ReviewGroupOut]
    uncategorized_lines: int
    suggestions_available: bool


class ResolveIn(BaseModel):
    """The category to give a merchant's lines, and the rule to keep, if any."""

    merchant_key: str = Field(min_length=1, max_length=200)
    category_id: int
    transaction_ids: list[int] | None = None
    save_rule: bool = True
    pattern: str | None = Field(default=None, max_length=200)
    match_type: MatchType = "contains"
    amount_min: Decimal | None = Field(default=None, ge=0)
    amount_max: Decimal | None = Field(default=None, ge=0)
    from_suggestion: bool = False


class ResolveOut(BaseModel):
    """What a resolve categorized, here and through the saved rule."""

    categorized: int
    rule_id: int | None
    also_by_rule: int
    waiting_by_rule: int = 0  # lines in statements not approved yet


class ApplyRulesOut(BaseModel):
    """What applying the rules to a batch categorized."""

    categorized: int
    batch: BatchOut


class TransactionPatch(BaseModel):
    """The fields of a line to change; only the fields sent are changed."""

    category_id: int | None = None
    notes: str | None = Field(default=None, max_length=1000)
    person: Owner | None = None
    counterparty_id: int | None = None  # null clears it
    # The month the line counts in (any day of it); null hands it back to the rule (ADR-089).
    counts_in: date | None = None


class PartIn(BaseModel):
    """One part of a split: its amount and category."""

    amount: Decimal
    category_id: int
    notes: str | None = Field(default=None, max_length=1000)


class SplitIn(BaseModel):
    """The parts to split a line into."""

    parts: list[PartIn] = Field(min_length=2, max_length=20)


class ChangeOut(_Out):
    """One logged change to a line."""

    change_id: int
    column_name: str
    old_value: str | None
    new_value: str | None
    reason: str
    changed_by: str
    changed_at: datetime


class AcceptedOut(BaseModel):
    """What accepting suggestions categorized."""

    merchants: int  # suggestions accepted (each saved as a rule)
    lines: int
    also_by_rule: int  # more lines those rules categorized, loaded or waiting


class SuggestOut(BaseModel):
    """How many merchants were asked about and how many got a suggestion."""

    asked: int
    suggested: int
    model: str


# ---------------- F10: transfers ----------------
class TransferLegOut(BaseModel):
    """The other side of a transfer."""

    transaction_id: int
    txn_date: date
    amount: Decimal
    description: str
    account_id: int | None
    account_name: str | None
    account_kind: str | None


class MatchOut(BaseModel):
    """How many transfer pairs were made."""

    pairs: int


# ---------------- F11: recurring entries ----------------
class TemplateIn(BaseModel):
    """A new recurring item (a bill or an income)."""

    name: str = Field(min_length=1, max_length=100)
    category_id: int
    type: Literal["income", "expense", "savings", "transfer", "debt_payment", "fee_interest"]
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=4)
    start_month: date
    end_month: date | None = None
    account_id: int | None = None
    person: Literal["Hernan", "Lauren", "Joint"] | None = None
    match_pattern: str | None = Field(default=None, max_length=200)
    tolerance_pct: Decimal = Field(default=Decimal(10), ge=0, le=100)
    notes: str | None = Field(default=None, max_length=400)
    # ADR-031: how often (1 monthly, 2-12 months, 0 once) and the usual day.
    every_months: Literal[0, 1, 2, 3, 4, 6, 12] = 1
    due_day: int | None = Field(default=None, ge=1, le=31)


class TemplatePatch(BaseModel):
    """The fields of a recurring item to change."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    category_id: int | None = None
    type: (
        Literal["income", "expense", "savings", "transfer", "debt_payment", "fee_interest"] | None
    ) = None
    account_id: int | None = None
    person: Literal["Hernan", "Lauren", "Joint"] | None = None
    match_pattern: str | None = Field(default=None, max_length=200)
    tolerance_pct: Decimal | None = Field(default=None, ge=0, le=100)
    end_month: date | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    notes: str | None = Field(default=None, max_length=400)
    every_months: Literal[0, 1, 2, 3, 4, 6, 12] | None = None
    due_day: int | None = Field(default=None, ge=1, le=31)


class TemplateOut(BaseModel):
    """A recurring item with its amounts over time."""

    template_id: int
    name: str
    category_id: int
    category_path: str | None
    type: str
    amount: Decimal | None  # in force in the current month (or the first month)
    amounts: list["AmountOut"]
    start_month: date
    end_month: date | None
    account_id: int | None
    account_name: str | None
    person: str | None
    match_pattern: str | None
    tolerance_pct: Decimal
    is_active: bool
    sort_order: int
    source: str
    group: str
    notes: str | None
    every_months: int = 1
    due_day: int | None = None


class AmountOut(BaseModel):
    """An amount and the month it applies from."""

    from_month: date
    amount: Decimal


class ChangeAmountIn(BaseModel):
    """A new amount from a month on."""

    from_month: date
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=4)


class MonthIn(BaseModel):
    """A month."""

    month: date


class CopyIn(BaseModel):
    """The month to copy and the months to copy it to."""

    from_month: date
    to_start: date
    to_end: date
    template_ids: list[int] | None = None


class EntryPatch(BaseModel):
    """The fields of one month's entry to change."""

    amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=4)
    reset: bool = False
    status: Literal["planned", "skipped"] | None = None
    notes: str | None = Field(default=None, max_length=400)


class LinkIn(BaseModel):
    """The line that paid an entry."""

    transaction_id: int


class CountOut(BaseModel):
    """How many were made or changed."""

    count: int


class FromExcelIn(BaseModel):
    """The workbook rows to turn into recurring items."""

    year: int = Field(ge=2019, le=2100)
    names: list[str] = Field(min_length=1, max_length=200)


class FromExcelOut(BaseModel):
    """What turning workbook rows into recurring items made."""

    templates: int
    entries: int
    linked: int


class ExcelRowOut(BaseModel):
    """A workbook row that could become a recurring item."""

    name: str
    group: str | None
    label: str
    block: str
    category_id: int | None
    category_path: str | None
    type: str | None
    months: int
    latest: Decimal
    suggested: bool
    exists: bool


class CellOut(BaseModel):
    """One recurring item in one month: expected, paid and its status."""

    month: date
    entry_id: int | None
    expected: Decimal | None
    actual: Decimal | None
    lines: int
    status: Literal["matched", "planned", "skipped", "not_generated", "none"]
    is_override: bool
    notes: str | None


class GridRowOut(BaseModel):
    """A recurring item across the year's months."""

    template_id: int
    name: str
    type: str
    group: str
    category_path: str | None
    is_active: bool
    cells: list[CellOut]


class GridOut(BaseModel):
    """A year of recurring items by month."""

    year: int
    months: list[date]
    excel_months: list[date]
    rows: list[GridRowOut]


class EntryOut(BaseModel):
    """One month of a recurring item with the lines that paid it."""

    entry_id: int
    template_id: int
    template_name: str
    month: date
    amount: Decimal
    template_amount: Decimal | None
    is_override: bool
    status: str
    notes: str | None
    tolerance: Decimal
    lines: list[TransactionOut]
    candidates: list[TransactionOut]


# ---------------- F12: month status ----------------
class StatusItemOut(BaseModel):
    """One thing to do for a month, with where to do it."""

    kind: Literal[
        "statement", "import", "uncategorized", "transfer", "recurring", "balance", "note"
    ]
    text: str
    link: str
    count: int


class CoverageOut(BaseModel):
    """How much of a month an account's data covers."""

    account_id: int
    state: Literal["full", "partial", "none"]
    covered_days: int
    days: int


class MonthStatusOut(BaseModel):
    """A month's data: its source, what covers it and what is missing."""

    month: date
    source: Literal["excel", "statements"]
    complete: bool
    items: list[StatusItemOut]
    coverage: list[CoverageOut]


class StatusAccountOut(BaseModel):
    """An account, as the status page names it."""

    account_id: int
    name: str
    kind: str
    owner: str


class LoadOut(BaseModel):
    """One load: when, what, how many rows and by whom."""

    loaded_at: datetime
    source: str
    file_name: str | None
    rows: int
    loaded_by: str


class TimelineStatementOut(BaseModel):
    """A statement on an account's timeline."""

    statement_file_id: int
    file_name: str
    start: date
    end: date
    state: Literal["loaded", "waiting", "problems", "not_read", "synced"]
    batch_id: int | None


class GapOut(BaseModel):
    """Days of an account no statement covers, and when the missing one is due."""

    start: date
    end: date
    due: date | None  # the current cycle: the bank issues its statement around this day
    closes: list[date] = []  # the statements that fill it, by closing day
    files: list[str] = []  # their usual file names, for banks that date them


class AccountTimelineOut(BaseModel):
    """An account's statements over time and the gaps between them."""

    account_id: int
    name: str
    closed_on: date | None
    opened_on: date | None = None
    start_day: int | None  # its statements usually start on this day of the month
    statements: list[TimelineStatementOut]
    gaps: list[GapOut]


class SourceOut(BaseModel):
    """How an account's data arrives and how fresh it is."""

    account_id: int
    name: str
    how: Literal["bank_sync", "email", "upload"]
    last_day: date | None
    state: Literal["up_to_date", "on_its_way", "on_import", "you_upload", "late"]
    note: str
    expected: date | None = None


class ScriptOut(BaseModel):
    """The Gmail script's heartbeat (ADR-078)."""

    state: Literal["ok", "silent", "never"]
    last_seen: datetime | None
    note: str


class StatusOut(BaseModel):
    """Everything the Data status page shows."""

    today: date
    excel_through: date | None
    accounts: list[StatusAccountOut]
    months: list[MonthStatusOut]
    loads: list[LoadOut]
    # Each account's statements in order and the days none covers (from the first month checked).
    statements: list[AccountTimelineOut] = []
    # How each account's data arrives and where it stands today (ADR-072).
    sources: list[SourceOut] = []
    script: ScriptOut | None = None


# ---------------- F13: spending analytics ----------------
class SpendCategoryOut(BaseModel):
    """A category's spending in a month against the month and the year before."""

    category_id: int
    name: str
    amount: Decimal
    prev: Decimal
    last_year: Decimal
    transactions: int


class SpendGroupOut(BaseModel):
    """A group's spending with its categories."""

    group_id: int
    name: str
    color: str | None
    amount: Decimal
    prev: Decimal
    last_year: Decimal
    transactions: int
    categories: list[SpendCategoryOut]


class SpendTotalOut(BaseModel):
    """The month's spending against the month and the year before."""

    amount: Decimal
    prev: Decimal
    last_year: Decimal
    transactions: int


class SpendSliceOut(BaseModel):
    """Spending for one value of a dimension (a person, a country, fixed or variable)."""

    key: str
    amount: Decimal
    transactions: int


class SpendMerchantOut(BaseModel):
    """A merchant's spending in the month."""

    merchant: str
    group_name: str
    amount: Decimal
    transactions: int


class SpendMonthOut(BaseModel):
    """A month's spending, for the trend."""

    month: date
    amount: Decimal


class SpendSeriesOut(BaseModel):
    """One series of the spending chart: a value per month."""

    key: str
    label: str
    color: str | None
    values: list[Decimal]


class SpendSeriesSetOut(BaseModel):
    """Spending by month, split by a dimension (ADR-094)."""

    months: list[date]
    by: str
    series: list[SpendSeriesOut]


class SpendingOut(BaseModel):
    """Everything the Spending page shows for a month."""

    month: date
    months: list[date]
    source: Literal["excel", "statements", "none"]
    total: SpendTotalOut
    groups: list[SpendGroupOut]
    by_person: list[SpendSliceOut]
    by_country: list[SpendSliceOut]
    fixed: list[SpendSliceOut]
    merchants: list[SpendMerchantOut]
    trend: list[SpendMonthOut]


class SpendLineOut(BaseModel):
    """One spending line."""

    transaction_id: int
    txn_date: date
    merchant: str
    description: str
    amount: Decimal
    category_name: str
    group_name: str
    person: str
    account_name: str | None
    source: str


# ---------------- F14: subscriptions and cost of debt ----------------
class ChargeOut(BaseModel):
    """One charge of a subscription."""

    transaction_id: int
    txn_date: date
    amount: Decimal
    description: str
    account_name: str | None


class SubscriptionOut(BaseModel):
    """A recurring charge: its cadence, what it costs and its charges."""

    merchant: str
    cadence: Literal["weekly", "monthly", "quarterly", "yearly", "possible"]
    typical: Decimal
    monthly_cost: Decimal
    yearly_cost: Decimal
    category_path: str | None
    accounts: list[str]
    charges: list[ChargeOut]
    last: date
    next_expected: date | None
    active: bool
    price_up: Decimal | None = None


class SubscriptionsOut(BaseModel):
    """Every subscription and what the active ones cost a month."""

    monthly_cost: Decimal  # active subscriptions with a known cadence
    weekly_monthly_cost: Decimal  # the weekly ones (app billing)
    subscriptions: list[SubscriptionOut]


class DebtAccountOut(BaseModel):
    """An account's interest and fees."""

    account_id: int | None
    name: str
    kind: str | None
    interest: Decimal
    fees: Decimal
    total: Decimal
    last_12: Decimal
    by_category: dict[str, Decimal]
    by_month: dict[date, Decimal]
    balance: Decimal | None
    balance_date: date | None


class DebtOut(BaseModel):
    """A year's cost of debt by account."""

    year: int
    years: list[int]
    through: date
    months: list[date]
    interest: Decimal
    fees: Decimal
    accounts: list[DebtAccountOut]


# ---------------- F14: balance sheet ----------------
HoldingClass = Literal[
    "property",
    "vehicle",
    "investment",
    "cash",
    "purchase",
    "loan",
    "personal_loan",
    "card",
    "other",
]
Positive = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=4)]


class HoldingIn(BaseModel):
    """Something new on the balance sheet, owned or owed."""

    name: str = Field(min_length=1, max_length=100)
    holding_class: HoldingClass
    side: Literal["asset", "liability"] | None = None
    value: Positive | None = None
    as_of: date | None = None
    target_amount: Positive | None = None
    installment: Positive | None = None
    full_price: Positive | None = None
    category_id: int | None = None
    recurring_template_id: int | None = None
    notes: str | None = Field(default=None, max_length=400)


class HoldingPatch(BaseModel):
    """The fields of a balance-sheet item to change."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    holding_class: HoldingClass | None = None
    side: Literal["asset", "liability"] | None = None
    target_amount: Positive | None = None
    installment: Positive | None = None
    full_price: Positive | None = None
    category_id: int | None = None
    recurring_template_id: int | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=400)


class ValueIn(BaseModel):
    """What an item was worth on a day."""

    as_of: date
    amount: Positive
    notes: str | None = Field(default=None, max_length=400)


class ValueOut(BaseModel):
    """A recorded value of an item."""

    snapshot_id: int | None
    as_of: date
    amount: Decimal
    source: str
    notes: str | None


class PurchaseOut(BaseModel):
    """A purchase in progress: paid, remaining and what is due at delivery."""

    target: Decimal
    paid: Decimal
    remaining: Decimal
    installment: Decimal | None
    installments_left: int | None
    full_price: Decimal | None
    at_delivery: Decimal | None
    lines: Decimal


class LoanScheduleOut(BaseModel):
    """A loan's amortization table in summary."""

    installments: int
    paid: int
    left: int
    next_period: date | None
    next_total: Decimal | None
    payoff: date | None
    balance: Decimal | None
    interest_this_year: Decimal
    interest_left: Decimal
    other_left: Decimal


class LoanOut(BaseModel):
    """A loan's payment and what was paid this year."""

    monthly_payment: Decimal | None
    paid_this_year: Decimal
    payments_this_year: int
    schedule: LoanScheduleOut | None = None


class LoanImportOut(BaseModel):
    """What reading a loan's table loaded."""

    installments: int
    paid: int
    due: int
    balance: Decimal | None
    as_of: date | None


class LoanPaymentOut(BaseModel):
    """One installment against the bank line that paid it."""

    number: int
    period: date
    total: Decimal
    status: Literal["paid", "due"]
    line_id: int | None
    line_date: date | None
    line_amount: Decimal | None
    line_description: str | None
    account_name: str | None


class SheetItemOut(BaseModel):
    """One item of the balance sheet."""

    key: str
    name: str
    side: Literal["asset", "liability"]
    holding_class: HoldingClass
    value: Decimal | None
    as_of: date | None
    source: str | None
    holding_id: int | None
    account_id: int | None
    is_active: bool
    notes: str | None
    history: list[ValueOut]
    purchase: PurchaseOut | None
    loan: LoanOut | None
    category_id: int | None
    recurring_template_id: int | None
    lines: Decimal | None = None  # a person's balance: their lines after the latest value


class SheetPointOut(BaseModel):
    """A month's assets, liabilities and net worth."""

    month: date
    assets: Decimal
    liabilities: Decimal
    net: Decimal


class BalanceSheetOut(BaseModel):
    """The balance sheet on a day with the trend of net worth."""

    as_of: date
    assets: Decimal
    liabilities: Decimal
    net_worth: Decimal
    commitments: Decimal
    items: list[SheetItemOut]
    series: list[SheetPointOut]


# ---------------- F15: projections ----------------
class ProjectionEventOut(BaseModel):
    """Something expected on a day: income, a bill, an installment or a what-if."""

    day: date
    name: str
    amount: Decimal
    kind: Literal["income", "fixed", "purchase", "variable", "change"]
    account_id: int | None = None


class ProjectionMonthOut(BaseModel):
    """A month of the forecast."""

    month: date
    income: Decimal
    fixed: Decimal
    variable: Decimal
    purchases: Decimal
    net: Decimal
    end_cash: Decimal
    items: list[ProjectionEventOut]
    # ADR-096: the likely range, and why the month differs from a usual one.
    end_cash_low: Decimal | None = None
    end_cash_high: Decimal | None = None
    seasonal: list["SeasonalNoteOut"] = []


class SeasonalNoteOut(BaseModel):
    """A group that makes a month heavier than usual, and by how much."""

    group_name: str
    extra: Decimal  # more than a usual month; negative is less


class ProjectionBandOut(BaseModel):
    """A day's likely range of cash."""

    day: date
    low: Decimal
    high: Decimal


class ProjectionDayOut(BaseModel):
    """A day's expected cash."""

    day: date
    balance: Decimal


class ProjectionAlertOut(BaseModel):
    """A group that spent well over its average."""

    month: date
    group_id: int
    group_name: str
    amount: Decimal
    average: Decimal
    change: Decimal | None


class ProjectionOut(BaseModel):
    """The cash forecast."""

    today: date
    start_cash: Decimal
    cash_as_of: date | None
    variable_per_month: Decimal
    average_months: list[date]
    months: list[ProjectionMonthOut]
    daily: list[ProjectionDayOut]
    lowest: ProjectionDayOut | None
    next_payday: ProjectionEventOut | None
    alerts: list[ProjectionAlertOut]
    # ADR-033
    horizon: int = 3
    average_over: int = 3
    floor: Decimal = Decimal(0)
    held: Decimal = Decimal(0)
    include_held: bool = False
    accounts: list["ProjectionAccountOut"] = []
    first_short: date | None = None
    end_cash: Decimal = Decimal(0)
    base: "ScenarioBaseOut | None" = None  # with what-ifs: the same without them
    # ADR-096
    band: list[ProjectionBandOut] = []
    chance_under_floor: Decimal | None = None
    seasons: bool = True
    seasonal_groups: int = 0
    seasons_from: Literal["groups", "all"] | None = None


class ProjectionAccountOut(BaseModel):
    """One bank account day by day, and what to move in to stay over the floor."""

    account_id: int
    name: str
    start: Decimal
    as_of: date | None
    daily: list[ProjectionDayOut]
    lowest: ProjectionDayOut
    under_floor: date | None
    move: Decimal


class ScenarioBaseOut(BaseModel):
    """The forecast without the what-ifs, to compare against."""

    lowest: ProjectionDayOut | None
    first_short: date | None
    end_cash: Decimal


class ChangeIn(BaseModel):
    """A what-if: an amount each month from a day, or once on a date."""

    name: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(max_digits=15, decimal_places=2)  # money in positive
    every: Literal["month", "once"] = "month"
    day: int = Field(default=1, ge=1, le=31)
    on: date | None = None
    account_id: int | None = None


class ScenarioIn(BaseModel):
    """The forecast's choices and the what-ifs to add."""

    horizon: Literal[1, 3, 12] = 3
    average_over: Literal[3, 6, 12] = 3
    floor: Decimal = Field(default=Decimal(0), ge=0, max_digits=15, decimal_places=2)
    include_held: bool = False
    seasons: bool = True
    changes: list[ChangeIn] = Field(default_factory=list, max_length=20)


TemplateOut.model_rebuild()
TransactionOut.model_rebuild()
ProjectionOut.model_rebuild()


# ---------------- F16: monthly report and export ----------------
class FindingOut(BaseModel):
    """One finding of a monthly report."""

    title: str
    text: str
    tone: Literal["good", "bad", "neutral"]


class ReportOut(BaseModel):
    """A month's report: its facts and findings."""

    month: date
    written_by: Literal["claude", "rules"]
    model: str | None
    generated_at: datetime | None
    generated_by: str
    facts: dict[str, Any]
    findings: list[FindingOut]
    notice: str | None = None


class ReportMonthsOut(BaseModel):
    """The months with or without a report."""

    months: list[date]
    claude: bool


class ExportDatasetOut(BaseModel):
    """A dataset that can be downloaded."""

    key: str
    title: str
    by: Literal["month", "year"]


# ---------------- F17: backups ----------------
class BackupStatusOut(BaseModel):
    """When the last backup and restore drill ran."""

    where: Literal["azure", "local"]
    backup: dict[str, Any] | None
    drill: dict[str, Any] | None
    backup_overdue: bool
    drill_overdue: bool
    error: str | None = None


# ---------------- F19: statements from a chosen month ----------------
class SourcesIn(BaseModel):
    """The first month whose statements count in place of the workbook."""

    statements_from: date | None  # any day of the month; null = the workbook wins every month


class GroupGapOut(BaseModel):
    """A group where workbook and statements disagree in a month."""

    group: str
    workbook: Decimal
    statements: Decimal
    difference: Decimal


class SourceMonthOut(BaseModel):
    """A month both the workbook and the statements cover, side by side."""

    month: date
    workbook_income: Decimal
    statements_income: Decimal
    workbook_spending: Decimal
    statements_spending: Decimal
    statement_lines: int
    groups: list[GroupGapOut]


class SourcesOut(BaseModel):
    """Where each month's numbers come from, and the months to check."""

    statements_from: date | None
    workbook_first: date | None
    workbook_last: date | None
    check: list[SourceMonthOut]


# ---------------- F22: Interactive Brokers ----------------
class PositionOut(BaseModel):
    """One investment position."""

    symbol: str
    description: str | None
    asset_class: str
    currency: str
    quantity: Decimal
    price: Decimal
    value: Decimal
    cost_basis: Decimal | None
    unrealized: Decimal | None


class PortfolioOut(BaseModel):
    """The investment account as the page shows it."""

    holding_id: int | None
    as_of: date | None
    total: Decimal | None
    cash: Decimal | None
    previous_total: Decimal | None
    previous_as_of: date | None
    stale: bool
    positions: list[PositionOut]


class PortfolioReadOut(BaseModel):
    """A portfolio as saved from the broker's report."""

    holding_id: int
    as_of: date
    total: Decimal
    cash: Decimal
    positions: int


# ---------------- F21: electronic invoices ----------------
class InvoiceLineOut(BaseModel):
    """A product on an invoice."""

    line_no: int
    description: str
    product_key: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    product_group: str | None
    group_source: str | None
    category_id: int | None = None
    category_path: str | None = None


class PaidWithOut(BaseModel):
    """The bank or card line that paid an invoice."""

    transaction_id: int
    txn_date: date
    account: str | None
    description: str


class InvoiceOut(BaseModel):
    """An electronic invoice with its products and payment."""

    invoice_id: int
    issuer_name: str
    number: str
    issue_date: date
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    received_by: str
    paid_with: PaidWithOut | None
    lines: list[InvoiceLineOut]


class GroupTotalOut(BaseModel):
    """A product group's total in the month."""

    group: str
    amount: Decimal
    lines: int


class UngroupedOut(BaseModel):
    """A product without a category yet."""

    product_key: str
    description: str
    lines: int
    amount: Decimal
    suggested_group: str | None


class PurchasesOut(BaseModel):
    """A month's purchases from invoices."""

    month: str
    total: Decimal
    matched_total: Decimal
    groups: list[GroupTotalOut]
    to_group: list[UngroupedOut]
    invoices: list[InvoiceOut]
    product_groups: list[str]
    suggestions_available: bool


class InvoiceUploadOut(BaseModel):
    """What happened to one uploaded invoice file."""

    file_name: str
    outcome: Literal["stored", "duplicate", "skipped", "rejected"]
    message: str
    invoice_id: int | None = None


class ProductGroupIn(BaseModel):
    """A product's grocery group, or its app category (ADR-050); send one of them."""

    product_key: str = Field(min_length=1, max_length=300)
    product_group: str | None = None
    category_id: int | None = None


class ProductGroupOut(BaseModel):
    """A product's category after it was set, and how many lines changed."""

    product_key: str
    product_group: str | None
    category_id: int | None = None
    lines_updated: int


class SuggestedOut(BaseModel):
    """How many products got a suggested group."""

    products: int


# ---------------- where a line came from (ADR-034) ----------------
class SourceTextOut(BaseModel):
    """A line of the statement's text near the line shown."""

    line_no: int
    text: str
    is_line: bool


class SimilarOut(BaseModel):
    """An earlier line like this one, with its category."""

    txn_date: date
    amount: Decimal
    description: str
    category_id: int | None
    category_path: str | None


class LineSourceOut(BaseModel):
    """Where a line came from: its statement, page and surrounding text."""

    transaction_id: int
    txn_date: date
    post_date: date | None
    amount: Decimal
    description: str
    account_name: str | None
    account_last4: str | None
    person: str | None
    pay_reference: str | None
    notes: str | None
    statement_file_id: int | None
    file_name: str | None
    bank: str | None
    period_start: date | None
    period_end: date | None
    page: int | None
    line_no: int | None
    section: str | None
    cardholder: str | None
    text: str | None
    around: list[SourceTextOut]
    note_from: str | None
    note_person: str | None
    note: str | None
    similar: list[SimilarOut]
    unreadable: bool
