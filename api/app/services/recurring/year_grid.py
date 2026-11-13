"""The year's recurring grid, and making recurring items from the workbook's rows."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    ExcelCell,
    RecurringEntry,
    RecurringTemplate,
    Transaction,
)
from app.services.excel_mapping import lookup, norm
from app.services.recurring.base import (
    EXCEL_SHEET,
    INCOME_TYPES,
    RecurringError,
    active_in,
    amount_for,
    amounts,
    months,
)
from app.services.recurring.matching import _excel_key, _template_key, excel_months, match
from app.services.recurring.templates import create_template


# ---------------------------------------------------------------- grid
@dataclass
class Cell:
    """A recurring item's month: expected, actual and its status."""

    month: date
    entry_id: int | None
    expected: Decimal | None
    actual: Decimal | None
    lines: int
    status: str  # matched, planned, skipped, not_generated, none
    is_override: bool
    notes: str | None


@dataclass
class Row:
    """A recurring item across the year."""

    template: RecurringTemplate
    group: str
    cells: list[Cell]


@dataclass
class Grid:
    """The year's recurring grid."""

    year: int
    months: list[date]
    rows: list[Row]
    excel_months: list[date]


def grid(db: Session, year: int) -> Grid:
    """A year of recurring items by month with their entries and the year's totals."""
    ms = months(date(year, 1, 1), date(year, 12, 1))
    entries = list(
        db.scalars(
            select(RecurringEntry).where(
                RecurringEntry.month >= ms[0], RecurringEntry.month <= ms[-1]
            )
        )
    )
    by_cell = {(e.template_id, e.month): e for e in entries}
    actual: dict[int, Decimal] = defaultdict(Decimal)
    count: dict[int, int] = defaultdict(int)
    if entries:
        for entry_id, amount in db.execute(
            select(Transaction.recurring_entry_id, Transaction.amount).where(
                Transaction.recurring_entry_id.in_([e.entry_id for e in entries])
            )
        ):
            if entry_id is not None:
                actual[entry_id] += amount
                count[entry_id] += 1
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    history = amounts(db)
    used = {e.template_id for e in entries}
    rows = []
    for t in db.scalars(
        select(RecurringTemplate).order_by(RecurringTemplate.sort_order, RecurringTemplate.name)
    ):
        if t.template_id not in used and not any(active_in(t, m) for m in ms):
            continue
        cells = []
        for m in ms:
            e = by_cell.get((t.template_id, m))
            if e is not None:
                status = "matched" if count[e.entry_id] else e.status
                cells.append(
                    Cell(
                        m,
                        e.entry_id,
                        e.amount,
                        actual[e.entry_id] if count[e.entry_id] else None,
                        count[e.entry_id],
                        status,
                        e.is_override,
                        e.notes,
                    )
                )
            elif active_in(t, m):
                cells.append(
                    Cell(
                        m,
                        None,
                        amount_for(history[t.template_id], m),
                        None,
                        0,
                        "not_generated",
                        False,
                        None,
                    )
                )
            else:
                cells.append(Cell(m, None, None, None, 0, "none", False, None))
        cat = cats.get(t.category_id)
        parent = cats.get(cat.parent_id) if cat and cat.parent_id else None
        group = t.excel_group or (parent.name if parent else cat.name if cat else "")
        rows.append(Row(t, group, cells))
    covered = sorted(m for m in excel_months(db) if m.year == year)
    return Grid(year, ms, rows, covered)


def plan_by_month(db: Session) -> dict[date, tuple[Decimal, Decimal]]:
    """Expected income and outflows per month from the planned entries (skips left out)."""
    out: dict[date, list[Decimal]] = {}
    q = (
        select(RecurringEntry.month, RecurringTemplate.type, func.sum(RecurringEntry.amount))
        .join(RecurringTemplate, RecurringTemplate.template_id == RecurringEntry.template_id)
        .where(RecurringEntry.status == "planned")
        .group_by(RecurringEntry.month, RecurringTemplate.type)
    )
    for month, type_, total in db.execute(q):
        item = out.setdefault(month, [Decimal(0), Decimal(0)])
        value = Decimal(str(total))
        if type_ in INCOME_TYPES:
            item[0] += value
        else:
            item[1] -= value
    return {m: (v[0], v[1]) for m, v in out.items()}


# ---------------------------------------------------------------- from the workbook
@dataclass
class ExcelRow:
    """A workbook row that could become a recurring item."""

    block: str
    group: str | None
    label: str
    name: str
    category_id: int | None
    category_path: str | None
    type: str | None
    person: str | None
    values: dict[date, Decimal]  # signed, by month
    suggested: bool
    exists: bool


def _paths(db: Session) -> dict[str, int]:
    cats = list(db.scalars(select(Category)))
    by_id = {c.category_id: c for c in cats}
    out = {}
    for c in cats:
        parent = by_id.get(c.parent_id) if c.parent_id is not None else None
        out[f"{parent.name}/{c.name}" if parent else c.name] = c.category_id
    return out


def excel_rows(db: Session, year: int) -> list[ExcelRow]:
    """The year's income and expense rows from the latest loaded workbook, in sheet order. A row
    is suggested when it has a value in at least three months or a planned value."""
    sheet = EXCEL_SHEET.format(year=year)
    import_id = db.scalar(select(func.max(ExcelCell.import_id)).where(ExcelCell.sheet == sheet))
    if import_id is None:
        return []
    cells = list(
        db.scalars(
            select(ExcelCell)
            .where(
                ExcelCell.import_id == import_id,
                ExcelCell.sheet == sheet,
                ExcelCell.block.in_(("income", "expense")),
                ExcelCell.month.is_not(None),
            )
            .order_by(ExcelCell.cell_id)
        )
    )
    paths = _paths(db)
    plan_from = max(excel_months(db), default=date(year, 1, 1))
    existing = {_template_key(t) for t in db.scalars(select(RecurringTemplate)) if t.excel_label}
    rows: dict[tuple[str, str, str], ExcelRow] = {}
    for c in cells:
        key = _excel_key(c.block, c.group_label, c.row_label)
        row = rows.get(key)
        if row is None:
            mapping = lookup(c.block, c.group_label, c.row_label)
            row = ExcelRow(
                block=c.block,
                group=c.group_label,
                label=c.row_label.strip(),
                name=c.row_label.strip(),
                category_id=paths.get(mapping.category) if mapping else None,
                category_path=mapping.category.replace("/", " / ") if mapping else None,
                type=mapping.type if mapping else None,
                person=mapping.person if mapping else None,
                values={},
                suggested=False,
                exists=key in existing,
            )
            rows[key] = row
        assert c.month is not None
        value = c.value if row.type == "income" else -c.value
        if value:
            row.values[c.month] = row.values.get(c.month, Decimal(0)) + value
    labels: dict[str, int] = defaultdict(int)
    for r in rows.values():
        labels[norm(r.label)] += 1
    out = []
    for r in rows.values():
        if not r.values:
            continue
        if labels[norm(r.label)] > 1 and r.group:
            r.name = f"{r.label} ({r.group.strip()})"
        planned = any(m > plan_from for m in r.values)
        r.suggested = (len(r.values) >= 3 or planned) and not r.exists and r.category_id is not None
        out.append(r)
    return out


def create_from_excel(db: Session, year: int, names: list[str], user: str) -> tuple[int, int, int]:
    """Make templates from the chosen workbook rows and fill the year: one entry per month with a
    value (the workbook's amount), then link the Excel history. Returns (templates, entries,
    lines linked)."""
    rows = {r.name: r for r in excel_rows(db, year)}
    unknown = [n for n in names if n not in rows]
    if unknown:
        raise RecurringError(f"Not rows of the {year} sheet: {', '.join(unknown)}.")
    order = list(rows)
    made = entries = 0
    for name in sorted(names, key=order.index):
        r = rows[name]
        if r.exists:
            continue
        if r.category_id is None or r.type is None:
            raise RecurringError(f"{name} has no category mapping.")
        ms = sorted(r.values)
        latest = r.values[ms[-1]]
        t = create_template(
            db,
            name=_unique_name(db, r.name),
            category_id=r.category_id,
            type_=r.type,
            amount=latest,
            start_month=ms[0],
            user=user,
            person=r.person,
            sort_order=order.index(name) + 1,
            source="excel",
            excel=(r.block, r.group, r.label),
        )
        for m in ms:
            value = r.values[m]
            db.add(
                RecurringEntry(
                    template_id=t.template_id, month=m, amount=value, is_override=value != latest
                )
            )
            entries += 1
        made += 1
    db.commit()
    linked = sum(match(db, m, user) for m in months(date(year, 1, 1), date(year, 12, 1)))
    return made, entries, linked


def _unique_name(db: Session, name: str) -> str:
    candidate, n = name[:100], 2
    while db.scalar(select(RecurringTemplate).where(RecurringTemplate.name == candidate)):
        candidate = f"{name[:95]} ({n})"
        n += 1
    return candidate
