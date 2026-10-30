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
CategoryKind = Literal["income", "expense", "savings", "transfer"]
MatchType = Literal["contains", "starts_with", "regex"]

HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- accounts ----------
class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    institution: str = Field(min_length=1, max_length=100)
    kind: AccountKind
    owner: Owner
    country: Country
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    is_active: bool = True


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    institution: str | None = Field(default=None, min_length=1, max_length=100)
    kind: AccountKind | None = None
    owner: Owner | None = None
    country: Country | None = None
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    is_active: bool | None = None


class AccountOut(_Out):
    account_id: int
    name: str
    institution: str
    kind: AccountKind
    owner: Owner
    country: Country
    last4: str | None
    is_active: bool


# ---------- categories ----------
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    kind: CategoryKind | None = None  # required for a group; a subcategory takes its parent's
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    is_fixed: bool = False


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    is_fixed: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class CategoryOut(_Out):
    category_id: int
    parent_id: int | None
    name: str
    kind: CategoryKind
    color: str | None
    is_fixed: bool
    is_active: bool
    sort_order: int


class CategoryGroup(CategoryOut):
    children: list[CategoryOut]


# ---------- merchant rules ----------
class RuleIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=200)
    match_type: MatchType = "contains"
    category_id: int
    priority: int = Field(default=50, ge=0, le=999)
    is_active: bool = True
    amount_min: Decimal | None = Field(default=None, ge=0)
    amount_max: Decimal | None = Field(default=None, ge=0)

    @field_validator("pattern")
    @classmethod
    def strip_pattern(cls, v: str) -> str:
        return v.strip()


class RulePatch(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    match_type: MatchType | None = None
    category_id: int | None = None
    priority: int | None = Field(default=None, ge=0, le=999)
    is_active: bool | None = None
    amount_min: Decimal | None = Field(default=None, ge=0)
    amount_max: Decimal | None = Field(default=None, ge=0)


class RuleOut(_Out):
    rule_id: int
    pattern: str
    match_type: MatchType
    category_id: int
    category_path: str
    priority: int
    is_active: bool
    amount_min: Decimal | None
    amount_max: Decimal | None


class RuleTestOut(BaseModel):
    description: str
    rule: RuleOut | None


# ---------------- F2: Excel history and cash flow ----------------
class MonthCheckOut(BaseModel):
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
    as_of: date
    name: str
    kind: str
    amount: Decimal
    notes: str


class YearTotalOut(BaseModel):
    year: int
    months: int
    income: Decimal
    outflows: Decimal


class UnmappedOut(BaseModel):
    sheet: str
    cell: str
    block: str
    group: str | None
    label: str
    value: Decimal


class HistoryPreviewOut(BaseModel):
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
    load_id: int
    transactions: int
    budget_rows: int
    snapshots: int
    raw_cells: int
    replaced_transactions: int


class MonthlyCashflowOut(BaseModel):
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
    month: date
    income: Decimal
    outflows: Decimal


# ---------------- F3: statements ----------------
class BatchRef(BaseModel):
    batch_id: int
    status: str
    tieout_ok: bool


class StatementAccountOut(_Out):
    account_id: int
    name: str
    last4: str | None


class StatementOut(_Out):
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
    file_name: str
    outcome: Literal["stored", "duplicate", "rejected"]
    message: str
    statement: StatementOut | None = None


class StatementPatch(BaseModel):
    account_ids: list[int] = Field(min_length=1, max_length=4)


# ---------------- F4: import batches and transactions ----------------
class CheckOut(BaseModel):
    name: str
    expected: Decimal
    actual: Decimal
    ok: bool


class StgLineOut(BaseModel):
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


class CategoryTotalOut(BaseModel):
    category_path: str
    type: str
    lines: int
    amount: Decimal


class RejectOut(BaseModel):
    page: int
    line_no: int
    text: str
    reason: str


class BatchOut(BaseModel):
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
    batch_id: int
    loaded: int
    skipped_duplicates: int


class TransactionOut(BaseModel):
    transaction_id: int
    txn_date: date
    post_date: date | None
    cash_month: date
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
    transfer_group_id: int | None = None
    transfer_with: "TransferLegOut | None" = None  # the other side of a matched transfer
    recurring_entry_id: int | None = None  # F11: the recurring entry this line pays


# ---------------- F9: classification ----------------
class SuggestionOut(BaseModel):
    category_id: int
    category_path: str
    confidence: Decimal
    reason: str
    model: str


class ReviewLineOut(BaseModel):
    transaction_id: int
    txn_date: date
    amount: Decimal
    description: str
    account_name: str | None
    person: str | None


class ReviewGroupOut(BaseModel):
    merchant_key: str
    lines: list[ReviewLineOut]
    total: Decimal
    suggestion: SuggestionOut | None


class ReviewOut(BaseModel):
    month: date | None
    groups: list[ReviewGroupOut]
    uncategorized_lines: int
    suggestions_available: bool


class ResolveIn(BaseModel):
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
    categorized: int
    rule_id: int | None
    also_by_rule: int


class TransactionPatch(BaseModel):
    category_id: int | None = None
    notes: str | None = Field(default=None, max_length=1000)
    person: Owner | None = None


class PartIn(BaseModel):
    amount: Decimal
    category_id: int
    notes: str | None = Field(default=None, max_length=1000)


class SplitIn(BaseModel):
    parts: list[PartIn] = Field(min_length=2, max_length=20)


class ChangeOut(_Out):
    change_id: int
    column_name: str
    old_value: str | None
    new_value: str | None
    reason: str
    changed_by: str
    changed_at: datetime


class SuggestOut(BaseModel):
    asked: int
    suggested: int
    model: str


# ---------------- F10: transfers ----------------
class TransferLegOut(BaseModel):
    transaction_id: int
    txn_date: date
    amount: Decimal
    description: str
    account_id: int | None
    account_name: str | None
    account_kind: str | None


class MatchOut(BaseModel):
    pairs: int


# ---------------- F11: recurring entries ----------------
class TemplateIn(BaseModel):
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


class TemplatePatch(BaseModel):
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


class TemplateOut(BaseModel):
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


class AmountOut(BaseModel):
    from_month: date
    amount: Decimal


class ChangeAmountIn(BaseModel):
    from_month: date
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=4)


class MonthIn(BaseModel):
    month: date


class CopyIn(BaseModel):
    from_month: date
    to_start: date
    to_end: date
    template_ids: list[int] | None = None


class EntryPatch(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=4)
    reset: bool = False
    status: Literal["planned", "skipped"] | None = None
    notes: str | None = Field(default=None, max_length=400)


class LinkIn(BaseModel):
    transaction_id: int


class CountOut(BaseModel):
    count: int


class FromExcelIn(BaseModel):
    year: int = Field(ge=2019, le=2100)
    names: list[str] = Field(min_length=1, max_length=200)


class FromExcelOut(BaseModel):
    templates: int
    entries: int
    linked: int


class ExcelRowOut(BaseModel):
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
    month: date
    entry_id: int | None
    expected: Decimal | None
    actual: Decimal | None
    lines: int
    status: Literal["matched", "planned", "skipped", "not_generated", "none"]
    is_override: bool
    notes: str | None


class GridRowOut(BaseModel):
    template_id: int
    name: str
    type: str
    group: str
    category_path: str | None
    is_active: bool
    cells: list[CellOut]


class GridOut(BaseModel):
    year: int
    months: list[date]
    excel_months: list[date]
    rows: list[GridRowOut]


class EntryOut(BaseModel):
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
    kind: Literal["statement", "import", "uncategorized", "transfer", "recurring", "balance"]
    text: str
    link: str
    count: int


class CoverageOut(BaseModel):
    account_id: int
    state: Literal["full", "partial", "none"]
    covered_days: int
    days: int


class MonthStatusOut(BaseModel):
    month: date
    source: Literal["excel", "statements"]
    complete: bool
    items: list[StatusItemOut]
    coverage: list[CoverageOut]


class StatusAccountOut(BaseModel):
    account_id: int
    name: str
    kind: str
    owner: str


class LoadOut(BaseModel):
    loaded_at: datetime
    source: str
    file_name: str | None
    rows: int
    loaded_by: str


class StatusOut(BaseModel):
    today: date
    excel_through: date | None
    accounts: list[StatusAccountOut]
    months: list[MonthStatusOut]
    loads: list[LoadOut]


# ---------------- F13: spending analytics ----------------
class SpendCategoryOut(BaseModel):
    category_id: int
    name: str
    amount: Decimal
    prev: Decimal
    last_year: Decimal
    transactions: int


class SpendGroupOut(BaseModel):
    group_id: int
    name: str
    color: str | None
    amount: Decimal
    prev: Decimal
    last_year: Decimal
    transactions: int
    categories: list[SpendCategoryOut]


class SpendTotalOut(BaseModel):
    amount: Decimal
    prev: Decimal
    last_year: Decimal
    transactions: int


class SpendSliceOut(BaseModel):
    key: str
    amount: Decimal
    transactions: int


class SpendMerchantOut(BaseModel):
    merchant: str
    group_name: str
    amount: Decimal
    transactions: int


class SpendMonthOut(BaseModel):
    month: date
    amount: Decimal


class SpendingOut(BaseModel):
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
    transaction_id: int
    txn_date: date
    amount: Decimal
    description: str
    account_name: str | None


class SubscriptionOut(BaseModel):
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


class SubscriptionsOut(BaseModel):
    monthly_cost: Decimal  # active subscriptions with a known cadence
    weekly_monthly_cost: Decimal  # the weekly ones (app billing)
    subscriptions: list[SubscriptionOut]


class DebtAccountOut(BaseModel):
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
    as_of: date
    amount: Positive
    notes: str | None = Field(default=None, max_length=400)


class ValueOut(BaseModel):
    snapshot_id: int | None
    as_of: date
    amount: Decimal
    source: str
    notes: str | None


class PurchaseOut(BaseModel):
    target: Decimal
    paid: Decimal
    remaining: Decimal
    installment: Decimal | None
    installments_left: int | None
    full_price: Decimal | None
    at_delivery: Decimal | None
    lines: Decimal


class LoanScheduleOut(BaseModel):
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
    monthly_payment: Decimal | None
    paid_this_year: Decimal
    payments_this_year: int
    schedule: LoanScheduleOut | None = None


class LoanImportOut(BaseModel):
    installments: int
    paid: int
    due: int
    balance: Decimal | None
    as_of: date | None


class LoanPaymentOut(BaseModel):
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


class SheetPointOut(BaseModel):
    month: date
    assets: Decimal
    liabilities: Decimal
    net: Decimal


class BalanceSheetOut(BaseModel):
    as_of: date
    assets: Decimal
    liabilities: Decimal
    net_worth: Decimal
    commitments: Decimal
    items: list[SheetItemOut]
    series: list[SheetPointOut]


# ---------------- F15: projections ----------------
class ProjectionEventOut(BaseModel):
    day: date
    name: str
    amount: Decimal
    kind: Literal["income", "fixed", "purchase", "variable"]


class ProjectionMonthOut(BaseModel):
    month: date
    income: Decimal
    fixed: Decimal
    variable: Decimal
    purchases: Decimal
    net: Decimal
    end_cash: Decimal
    items: list[ProjectionEventOut]


class ProjectionDayOut(BaseModel):
    day: date
    balance: Decimal


class ProjectionAlertOut(BaseModel):
    month: date
    group_id: int
    group_name: str
    amount: Decimal
    average: Decimal
    change: Decimal | None


class ProjectionOut(BaseModel):
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


TemplateOut.model_rebuild()
TransactionOut.model_rebuild()


# ---------------- F16: monthly report and export ----------------
class FindingOut(BaseModel):
    title: str
    text: str
    tone: Literal["good", "bad", "neutral"]


class ReportOut(BaseModel):
    month: date
    written_by: Literal["claude", "rules"]
    model: str | None
    generated_at: datetime | None
    generated_by: str
    facts: dict[str, Any]
    findings: list[FindingOut]
    notice: str | None = None


class ReportMonthsOut(BaseModel):
    months: list[date]
    claude: bool


class ExportDatasetOut(BaseModel):
    key: str
    title: str
    by: Literal["month", "year"]


# ---------------- F17: backups ----------------
class BackupStatusOut(BaseModel):
    where: Literal["azure", "local"]
    backup: dict[str, Any] | None
    drill: dict[str, Any] | None
    backup_overdue: bool
    drill_overdue: bool
    error: str | None = None


# ---------------- F19: statements from a chosen month ----------------
class SourcesIn(BaseModel):
    statements_from: date | None  # any day of the month; null = the workbook wins every month


class GroupGapOut(BaseModel):
    group: str
    workbook: Decimal
    statements: Decimal
    difference: Decimal


class SourceMonthOut(BaseModel):
    month: date
    workbook_income: Decimal
    statements_income: Decimal
    workbook_spending: Decimal
    statements_spending: Decimal
    statement_lines: int
    groups: list[GroupGapOut]


class SourcesOut(BaseModel):
    statements_from: date | None
    workbook_first: date | None
    workbook_last: date | None
    check: list[SourceMonthOut]


# ---------------- F22: Interactive Brokers ----------------
class PositionOut(BaseModel):
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
    holding_id: int | None
    as_of: date | None
    total: Decimal | None
    cash: Decimal | None
    previous_total: Decimal | None
    previous_as_of: date | None
    stale: bool
    positions: list[PositionOut]


class PortfolioReadOut(BaseModel):
    holding_id: int
    as_of: date
    total: Decimal
    cash: Decimal
    positions: int


# ---------------- F21: electronic invoices ----------------
class InvoiceLineOut(BaseModel):
    line_no: int
    description: str
    product_key: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    product_group: str | None
    group_source: str | None


class PaidWithOut(BaseModel):
    transaction_id: int
    txn_date: date
    account: str | None
    description: str


class InvoiceOut(BaseModel):
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
    group: str
    amount: Decimal
    lines: int


class UngroupedOut(BaseModel):
    product_key: str
    description: str
    lines: int
    amount: Decimal
    suggested_group: str | None


class PurchasesOut(BaseModel):
    month: str
    total: Decimal
    matched_total: Decimal
    groups: list[GroupTotalOut]
    to_group: list[UngroupedOut]
    invoices: list[InvoiceOut]
    product_groups: list[str]
    suggestions_available: bool


class InvoiceUploadOut(BaseModel):
    file_name: str
    outcome: Literal["stored", "duplicate", "skipped", "rejected"]
    message: str
    invoice_id: int | None = None


class ProductGroupIn(BaseModel):
    product_key: str = Field(min_length=1, max_length=300)
    product_group: str


class ProductGroupOut(BaseModel):
    product_key: str
    product_group: str
    lines_updated: int


class SuggestedOut(BaseModel):
    products: int
