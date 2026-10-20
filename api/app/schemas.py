"""Request and response models: reference data (F1), history and cash flow (F2).

Money is Decimal and serializes as a JSON string, so no precision is lost on the way to the UI.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

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


class RuleOut(_Out):
    rule_id: int
    pattern: str
    match_type: MatchType
    category_id: int
    category_path: str
    priority: int
    is_active: bool


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
