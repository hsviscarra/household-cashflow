"""Explore (ADR-099, plan item B4): build a view of spending. Pick what to measure, what goes
in the rows and the columns, a period and a filter; get a table to read or chart.

The database groups the spending lines (`mart.v_spending_line`, the same lines every spending
page reads) by the two dimensions; `pivot` turns those groups into the table. Sums and counts
are kept side by side to the end, so an average is right in every cell and every total.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import v_spending_line as v
from app.services.recurring import add_months, first

# Limits (ADR-099): a view is something to read, not an export.
MAX_ROWS = 50
MAX_COLS = 24
MAX_MONTHS = 60
MEASURES = ("amount", "lines", "average")
DIMENSIONS = (
    "month",
    "year",
    "group",
    "category",
    "person",
    "account",
    "country",
    "merchant",
    "kind",
)
IN_TIME = ("month", "year")  # read in order, never folded or ranked
REST = "Everything else"
NOT_SET = "Not set"

ZERO = Decimal(0)
CENT = Decimal("0.01")


class ExploreError(ValueError):
    """The view asked for can't be built; the message says why."""


@dataclass(frozen=True)
class Spec:
    """A view as asked for: the measure, the two dimensions, the months and the filter."""

    measure: str
    rows: str
    cols: str | None
    start: date  # first month
    end: date  # last month
    person: str | None = None
    group_id: int | None = None
    category_id: int | None = None
    account_id: int | None = None
    country: str | None = None


@dataclass(frozen=True)
class Record:
    """One group from the database: its place in rows and columns, and what it adds up to."""

    row: str
    col: str
    amount: Decimal
    lines: int


@dataclass
class Cell:
    """A sum and a count kept together, so any measure can be read from it."""

    amount: Decimal = ZERO
    lines: int = 0

    def add(self, amount: Decimal, lines: int) -> None:
        """Add a sum and its count."""
        self.amount += amount
        self.lines += lines

    def value(self, measure: str) -> Decimal:
        """The cell in the chosen measure: the amount, the number of lines or the average line."""
        if measure == "lines":
            return Decimal(self.lines)
        if measure == "average":
            return (self.amount / self.lines).quantize(CENT) if self.lines else ZERO
        return self.amount


@dataclass
class Pivot:
    """The finished table: row and column names, the cells and every total."""

    rows: list[str]
    cols: list[str]
    cells: list[list[Decimal]]
    row_totals: list[Decimal]
    col_totals: list[Decimal]
    total: Decimal
    folded: int  # rows added together into the last one


def check(spec: Spec) -> None:
    """Refuse a view that can't be built, saying why (ExploreError)."""
    if spec.measure not in MEASURES:
        raise ExploreError(f"Measure is one of: {', '.join(MEASURES)}.")
    if spec.rows not in DIMENSIONS or (spec.cols is not None and spec.cols not in DIMENSIONS):
        raise ExploreError(f"Rows and columns are one of: {', '.join(DIMENSIONS)}.")
    if spec.rows == spec.cols:
        raise ExploreError("Rows and columns can't be the same.")
    if spec.start > spec.end:
        raise ExploreError("The period starts after it ends.")
    if add_months(first(spec.start), MAX_MONTHS) <= first(spec.end):
        raise ExploreError(f"The period is at most {MAX_MONTHS} months.")


def _column(dimension: str) -> ColumnElement[Any]:
    """The view's column a dimension is grouped by (years are months, rolled up after)."""
    return {
        "month": v.c.cash_month,
        "year": v.c.cash_month,
        "group": v.c.group_name,
        "category": v.c.category_name,
        "person": v.c.person,
        "account": v.c.account_name,
        "country": v.c.country,
        "merchant": v.c.merchant,
        "kind": v.c.is_fixed,
    }[dimension]


def label(dimension: str, value: object) -> str:
    """What a group is called in the table."""
    if value is None:
        return "Cash Flow sheet" if dimension == "account" else NOT_SET
    if dimension == "month" and isinstance(value, date):
        return value.strftime("%Y-%m")
    if dimension == "year" and isinstance(value, date):
        return str(value.year)
    if dimension == "kind":
        return "Fixed" if value else "Variable"
    return str(value)


def records(db: Session, spec: Spec) -> list[Record]:
    """The spending lines of the period, grouped by the database into one record per cell."""
    row = _column(spec.rows)
    grouped = [row] if spec.cols is None else [row, _column(spec.cols)]
    # Two dimensions on the same column (month and year): group once, read twice.
    by = list(dict.fromkeys(grouped))
    q = (
        select(*by, func.sum(v.c.amount), func.count())
        .where(v.c.cash_month >= first(spec.start), v.c.cash_month <= first(spec.end))
        .group_by(*by)
    )
    for column, wanted in (
        (v.c.person, spec.person),
        (v.c.group_id, spec.group_id),
        (v.c.category_id, spec.category_id),
        (v.c.account_id, spec.account_id),
        (v.c.country, spec.country),
    ):
        if wanted is not None:
            q = q.where(column == wanted)
    out = []
    for found in db.execute(q).all():
        values = dict(zip(by, found[: len(by)], strict=True))
        out.append(
            Record(
                label(spec.rows, values[row]),
                "" if spec.cols is None else label(spec.cols, values[_column(spec.cols)]),
                Decimal(str(found[-2] or 0)),
                int(found[-1]),
            )
        )
    return out


def _ordered(names: dict[str, Cell], dimension: str | None, limit: int) -> tuple[list[str], int]:
    """Names in reading order (time ascending, the rest biggest first) and how many didn't fit."""
    if dimension in IN_TIME:
        ordered = sorted(names)
        return ordered[-limit:], 0  # the most recent when there are too many
    ranked = sorted(names, key=lambda n: (-names[n].amount, n))
    return ranked[:limit], max(0, len(ranked) - limit)


def pivot(found: list[Record], spec: Spec) -> Pivot:
    """Lay the records out as a table: order the rows and columns, fold what doesn't fit
    into one last row, and total everything in the chosen measure."""
    by_row: dict[str, Cell] = defaultdict(Cell)
    by_col: dict[str, Cell] = defaultdict(Cell)
    grid: dict[tuple[str, str], Cell] = defaultdict(Cell)
    for r in found:
        by_row[r.row].add(r.amount, r.lines)
        by_col[r.col].add(r.amount, r.lines)
        grid[(r.row, r.col)].add(r.amount, r.lines)
    rows, folded = _ordered(by_row, spec.rows, MAX_ROWS)
    cols, _ = _ordered(by_col, spec.cols, MAX_COLS) if spec.cols else ([""], 0)
    if folded:  # what didn't fit adds up into one last row
        kept = set(rows)
        for (row, col), cell in list(grid.items()):
            if row not in kept:
                grid[(REST, col)].add(cell.amount, cell.lines)
                by_row[REST].add(cell.amount, cell.lines)
        rows.append(REST)
    shown_cols = set(cols)
    total, col_totals = Cell(), {c: Cell() for c in cols}
    row_totals = {r: Cell() for r in rows}
    for (row, col), cell in grid.items():
        if row in row_totals and col in shown_cols:
            row_totals[row].add(cell.amount, cell.lines)
            col_totals[col].add(cell.amount, cell.lines)
            total.add(cell.amount, cell.lines)
    m = spec.measure
    return Pivot(
        rows,
        cols if spec.cols else [],
        [[grid[(r, c)].value(m) if (r, c) in grid else ZERO for c in cols] for r in rows],
        [row_totals[r].value(m) for r in rows],
        [col_totals[c].value(m) for c in cols] if spec.cols else [],
        total.value(m),
        folded,
    )


def build(db: Session, spec: Spec) -> Pivot:
    """Check the view, ask the database and lay out the table."""
    check(spec)
    return pivot(records(db, spec), spec)
