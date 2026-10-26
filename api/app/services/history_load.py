"""Preview and load the Excel history (F2).

Load replaces all earlier Excel history in one database transaction: the workbook is the source,
so loading a corrected copy swaps the old rows for the new ones. Raw cells of every load are kept.
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    BalanceSnapshot,
    Budget,
    Category,
    ExcelCell,
    ExcelImport,
    LoadLog,
    Transaction,
)
from app.schemas import (
    HistoryLoadOut,
    HistoryPreviewOut,
    MappingReviewOut,
    MonthCheckOut,
    SnapshotOut,
    UnmappedOut,
    YearTotalOut,
)
from app.services.excel_history import ParsedWorkbook
from app.services.excel_mapping import Mapping

SOURCE = "excel_history"
PLAN_SOURCE = "excel_plan"
SNAPSHOT_SOURCE = "excel"


@dataclass
class _Review:
    mapping: Mapping
    total: Decimal = Decimal(0)
    months: set[date] = field(default_factory=set)


class HistoryError(Exception):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preview(
    db: Session, parsed: ParsedWorkbook, file_name: str, file_sha256: str
) -> HistoryPreviewOut:
    actual = parsed.actual_rows
    months = sorted({r.cell.month for r in actual if r.cell.month})

    years: dict[int, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    year_months: dict[int, set[date]] = defaultdict(set)
    for r in actual:
        assert r.cell.month is not None
        y = r.cell.month.year
        year_months[y].add(r.cell.month)
        if r.mapping.type == "income":
            years[y][0] += r.cell.value
        else:
            years[y][1] += r.cell.value

    review: dict[tuple[str, str | None, str], _Review] = {}
    for r in parsed.rows:
        # One line per label and mapping, across sheets and group headers.
        key = (r.cell.block, r.mapping.category, r.cell.label)
        item = review.setdefault(key, _Review(r.mapping))
        if not r.is_plan and r.cell.month is not None:
            item.total += r.cell.value
            item.months.add(r.cell.month)

    already = db.scalar(
        select(func.count()).select_from(ExcelImport).where(ExcelImport.file_sha256 == file_sha256)
    )
    return HistoryPreviewOut(
        file_name=file_name,
        file_sha256=file_sha256,
        already_loaded=bool(already),
        first_month=months[0] if months else None,
        last_month=months[-1] if months else None,
        months=len(months),
        actual_rows=len(actual),
        plan_rows=len(parsed.plan_rows),
        plan_months=sorted({r.cell.month for r in parsed.plan_rows if r.cell.month}),
        years=[
            YearTotalOut(year=y, months=len(year_months[y]), income=v[0], outflows=v[1])
            for y, v in sorted(years.items())
        ],
        mismatches=[
            MonthCheckOut(
                month=c.month,
                sheet=c.sheet,
                income_rows=c.income_rows,
                income_workbook=c.income_workbook,
                expense_rows=c.expense_rows,
                expense_workbook=c.expense_workbook,
                left_out=c.left_out,
                typed_total=c.typed_total,
                explained=c.explained,
            )
            for c in sorted(parsed.checks, key=lambda c: c.month)
            if not c.matches
        ],
        unmapped=[
            UnmappedOut(
                sheet=c.sheet,
                cell=c.cell,
                block=c.block,
                group=c.group,
                label=c.label,
                value=c.value,
            )
            for c in parsed.unmapped
        ],
        mapping=sorted(
            (
                MappingReviewOut(
                    block=k[0],
                    group=None,
                    label=k[2],
                    type=v.mapping.type,
                    category=v.mapping.category,
                    person=v.mapping.person,
                    months=len(v.months),
                    total=v.total,
                    review=v.mapping.review,
                )
                for k, v in review.items()
            ),
            key=lambda m: (m.review is None, m.block != "income", m.category, m.label),
        ),
        snapshots=[
            SnapshotOut(as_of=s.as_of, name=s.name, kind=s.kind, amount=s.amount, notes=s.notes)
            for s in parsed.snapshots
        ],
        side_cells=sum(1 for c in parsed.cells if c.block.startswith("side:")),
    )


@dataclass
class _Cat:
    category_id: int
    is_fixed: bool


def _category_ids(db: Session) -> dict[str, _Cat]:
    cats = list(db.scalars(select(Category)))
    by_id = {c.category_id: c for c in cats}
    out: dict[str, _Cat] = {}
    for c in cats:
        parent = by_id.get(c.parent_id) if c.parent_id is not None else None
        path = f"{parent.name}/{c.name}" if parent else c.name
        out[path] = _Cat(c.category_id, c.is_fixed)
    return out


def load(
    db: Session, parsed: ParsedWorkbook, file_name: str, file_sha256: str, user: str
) -> HistoryLoadOut:
    if parsed.unmapped:
        labels = sorted({c.label for c in parsed.unmapped})
        raise HistoryError(f"Rows without a category mapping: {', '.join(labels)}.", 422)
    if not parsed.rows:
        raise HistoryError("No Cash Flow sheets with values were found in this file.", 422)
    exists = db.scalar(select(ExcelImport).where(ExcelImport.file_sha256 == file_sha256))
    if exists is not None:
        raise HistoryError("This exact workbook is already loaded.", 409)

    cats = _category_ids(db)
    missing = sorted({r.mapping.category for r in parsed.rows if r.mapping.category not in cats})
    if missing:
        raise HistoryError(f"Categories missing in the database: {', '.join(missing)}.", 422)

    try:
        imp = ExcelImport(file_sha256=file_sha256, file_name=file_name[:260], loaded_by=user)
        db.add(imp)
        db.flush()

        raw: dict[tuple[str, str], ExcelCell] = {}
        for c in parsed.cells:
            cell = ExcelCell(
                import_id=imp.import_id,
                sheet=c.sheet,
                cell=c.cell,
                block=c.block,
                group_label=c.group,
                row_label=c.label[:100],
                month=c.month,
                value=c.value,
            )
            raw[(c.sheet, c.cell)] = cell
        db.add_all(raw.values())
        db.flush()

        replaced = db.scalar(
            select(func.count()).select_from(Transaction).where(Transaction.source == SOURCE)
        )
        db.execute(delete(Transaction).where(Transaction.source == SOURCE))
        db.execute(delete(Budget).where(Budget.source == PLAN_SOURCE))
        db.execute(delete(BalanceSnapshot).where(BalanceSnapshot.source == SNAPSHOT_SOURCE))

        txns = []
        for r in parsed.actual_rows:
            assert r.cell.month is not None
            cat = cats[r.mapping.category]
            where = f"{r.cell.sheet}!{r.cell.cell}"
            txns.append(
                Transaction(
                    natural_key=r.natural_key,
                    excel_cell_id=raw[(r.cell.sheet, r.cell.cell)].cell_id,
                    txn_date=r.cell.month,
                    cash_month=r.cell.month,
                    amount=r.signed_amount,
                    description_raw=r.cell.label[:400],
                    notes=f"{where} ({r.cell.group})" if r.cell.group else where,
                    type=r.mapping.type,
                    category_id=cat.category_id,
                    category_source="excel",
                    person=r.mapping.person,
                    country=r.mapping.country,
                    is_fixed=cat.is_fixed,
                    source=SOURCE,
                    status="confirmed",
                )
            )
        db.add_all(txns)

        plan: dict[tuple[date, int, str], tuple[str, Decimal]] = {}
        for r in parsed.plan_rows:
            assert r.cell.month is not None
            key = (r.cell.month, cats[r.mapping.category].category_id, r.cell.label[:100])
            prev = plan.get(key, (r.mapping.type, Decimal(0)))[1]
            plan[key] = (r.mapping.type, prev + r.signed_amount)
        db.add_all(
            Budget(month=m, category_id=cid, label=label, type=t, amount=amt, source=PLAN_SOURCE)
            for (m, cid, label), (t, amt) in plan.items()
        )

        db.add_all(
            BalanceSnapshot(
                as_of=s.as_of,
                name=s.name[:100],
                kind=s.kind,
                amount=s.amount,
                source=SNAPSHOT_SOURCE,
                notes=s.notes[:400],
            )
            for s in parsed.snapshots
        )

        log = LoadLog(
            source=SOURCE,
            file_sha256=file_sha256,
            loaded_by=user,
            rows_loaded=len(txns),
            summary=json.dumps(
                {
                    "file_name": file_name,
                    "transactions": len(txns),
                    "budget_rows": len(plan),
                    "snapshots": len(parsed.snapshots),
                    "raw_cells": len(raw),
                    "replaced_transactions": replaced or 0,
                    "unexplained_months": [
                        c.month.isoformat() for c in parsed.checks if not c.explained
                    ],
                }
            ),
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return HistoryLoadOut(
        load_id=log.load_id,
        transactions=len(txns),
        budget_rows=len(plan),
        snapshots=len(parsed.snapshots),
        raw_cells=len(raw),
        replaced_transactions=replaced or 0,
    )
