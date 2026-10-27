"""Recurring entries (F11, ADR-008): templates, month entries, matching and the month grid."""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion.preview import category_paths
from app.models import Account, Category, RecurringTemplate, Transaction
from app.routers.classify import transaction_out
from app.schemas import (
    AmountOut,
    CellOut,
    ChangeAmountIn,
    CopyIn,
    CountOut,
    EntryOut,
    EntryPatch,
    ExcelRowOut,
    FromExcelIn,
    FromExcelOut,
    GridOut,
    GridRowOut,
    LinkIn,
    MonthIn,
    TemplateIn,
    TemplateOut,
    TemplatePatch,
    TransactionOut,
)
from app.services import recurring

router = APIRouter(prefix="/api/recurring", tags=["recurring"])
DB = Annotated[Session, Depends(get_session)]


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


def _run[T](fn: Callable[[], T]) -> T:
    try:
        return fn()
    except recurring.RecurringError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


def _template_out(db: Session, t: RecurringTemplate) -> TemplateOut:
    paths = category_paths(db)
    history = recurring.amounts(db, [t.template_id])[t.template_id]
    today = recurring.first(date.today())
    current = recurring.amount_for(history, max(today, t.start_month))
    cat = db.get(Category, t.category_id)
    parent = db.get(Category, cat.parent_id) if cat and cat.parent_id else None
    account = db.get(Account, t.account_id) if t.account_id else None
    return TemplateOut(
        template_id=t.template_id,
        name=t.name,
        category_id=t.category_id,
        category_path=paths.get(t.category_id),
        type=t.type,
        amount=abs(current) if current is not None else None,
        amounts=[AmountOut(from_month=a.from_month, amount=abs(a.amount)) for a in history],
        start_month=t.start_month,
        end_month=t.end_month,
        account_id=t.account_id,
        account_name=account.name if account else None,
        person=t.person,
        match_pattern=t.match_pattern,
        tolerance_pct=t.tolerance_pct,
        is_active=t.is_active,
        sort_order=t.sort_order,
        source=t.source,
        group=t.excel_group or (parent.name if parent else cat.name if cat else ""),
        notes=t.notes,
    )


def _lines_out(db: Session, rows: list[Transaction]) -> list[TransactionOut]:
    paths = category_paths(db)
    names = {a.account_id: a.name for a in db.scalars(select(Account))}
    return [transaction_out(r, names.get(r.account_id or -1), paths) for r in rows]


# ---------------------------------------------------------------- templates
@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: DB) -> list[TemplateOut]:
    rows = db.scalars(
        select(RecurringTemplate).order_by(RecurringTemplate.sort_order, RecurringTemplate.name)
    )
    return [_template_out(db, t) for t in rows]


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateIn, db: DB, request: Request) -> TemplateOut:
    t = _run(
        lambda: recurring.create_template(
            db,
            name=body.name,
            category_id=body.category_id,
            type_=body.type,
            amount=body.amount,
            start_month=body.start_month,
            end_month=body.end_month,
            account_id=body.account_id,
            person=body.person,
            match_pattern=body.match_pattern,
            tolerance_pct=body.tolerance_pct,
            notes=body.notes,
            user=_user(request),
        )
    )
    db.commit()
    return _template_out(db, t)


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, body: TemplatePatch, db: DB, request: Request) -> TemplateOut:
    changes = body.model_dump(exclude_unset=True)
    _run(lambda: recurring.update_template(db, template_id, changes, _user(request)))
    return _template_out(db, recurring.get_template(db, template_id))


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, db: DB, request: Request) -> Response:
    _run(lambda: recurring.delete_template(db, template_id, _user(request)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/templates/{template_id}/amount", response_model=CountOut)
def change_amount(template_id: int, body: ChangeAmountIn, db: DB, request: Request) -> CountOut:
    n = _run(
        lambda: recurring.change_amount(
            db, template_id, body.from_month, body.amount, _user(request)
        )
    )
    return CountOut(count=n)


# ---------------------------------------------------------------- months
@router.post("/generate", response_model=CountOut)
def generate(body: MonthIn, db: DB, request: Request) -> CountOut:
    return CountOut(count=recurring.generate(db, body.month, _user(request)))


@router.post("/copy", response_model=CountOut)
def copy(body: CopyIn, db: DB, request: Request) -> CountOut:
    n = _run(
        lambda: recurring.copy(
            db, body.from_month, body.to_start, body.to_end, _user(request), body.template_ids
        )
    )
    return CountOut(count=n)


@router.post("/match", response_model=CountOut)
def match(db: DB, request: Request) -> CountOut:
    return CountOut(count=recurring.match_all(db, _user(request)))


@router.get("/grid", response_model=GridOut)
def grid(db: DB, year: Annotated[int, Query(ge=2019, le=2100)]) -> GridOut:
    g = recurring.grid(db, year)
    paths = category_paths(db)
    return GridOut(
        year=g.year,
        months=g.months,
        excel_months=g.excel_months,
        rows=[
            GridRowOut(
                template_id=r.template.template_id,
                name=r.template.name,
                type=r.template.type,
                group=r.group,
                category_path=paths.get(r.template.category_id),
                is_active=r.template.is_active,
                cells=[CellOut(**vars(c)) for c in r.cells],
            )
            for r in g.rows
        ],
    )


# ---------------------------------------------------------------- entries
def _entry_out(db: Session, entry_id: int) -> EntryOut:
    e = recurring.get_entry(db, entry_id)
    t = recurring.get_template(db, e.template_id)
    default = recurring.amount_for(recurring.amounts(db, [t.template_id])[t.template_id], e.month)
    lines = list(db.scalars(select(Transaction).where(Transaction.recurring_entry_id == entry_id)))
    return EntryOut(
        entry_id=e.entry_id,
        template_id=t.template_id,
        template_name=t.name,
        month=e.month,
        amount=e.amount,
        template_amount=default,
        is_override=e.is_override,
        status=e.status,
        notes=e.notes,
        tolerance=recurring.tolerance(t, e.amount),
        lines=_lines_out(db, lines),
        candidates=_lines_out(db, recurring.candidates(db, entry_id)),
    )


@router.get("/entries/{entry_id}", response_model=EntryOut)
def get_entry(entry_id: int, db: DB) -> EntryOut:
    return _run(lambda: _entry_out(db, entry_id))


@router.patch("/entries/{entry_id}", response_model=EntryOut)
def edit_entry(entry_id: int, body: EntryPatch, db: DB, request: Request) -> EntryOut:
    _run(
        lambda: recurring.edit_entry(
            db,
            entry_id,
            _user(request),
            amount=body.amount,
            reset=body.reset,
            status=body.status,
            notes=body.notes,
        )
    )
    return _entry_out(db, entry_id)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, db: DB, request: Request) -> Response:
    _run(lambda: recurring.delete_entry(db, entry_id, _user(request)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/entries/{entry_id}/lines", response_model=EntryOut)
def link_line(entry_id: int, body: LinkIn, db: DB, request: Request) -> EntryOut:
    _run(lambda: recurring.link_line(db, entry_id, body.transaction_id, _user(request)))
    return _entry_out(db, entry_id)


@router.delete("/lines/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_line(transaction_id: int, db: DB, request: Request) -> Response:
    _run(lambda: recurring.unlink_line(db, transaction_id, _user(request)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- from the workbook
@router.get("/excel-rows", response_model=list[ExcelRowOut])
def excel_rows(db: DB, year: Annotated[int, Query(ge=2019, le=2100)]) -> list[ExcelRowOut]:
    out = []
    for r in recurring.excel_rows(db, year):
        latest = r.values[max(r.values)]
        out.append(
            ExcelRowOut(
                name=r.name,
                group=r.group,
                label=r.label,
                block=r.block,
                category_id=r.category_id,
                category_path=r.category_path,
                type=r.type,
                months=len(r.values),
                latest=abs(latest),
                suggested=r.suggested,
                exists=r.exists,
            )
        )
    return out


@router.post("/from-excel", response_model=FromExcelOut)
def from_excel(body: FromExcelIn, db: DB, request: Request) -> FromExcelOut:
    made, entries, linked = _run(
        lambda: recurring.create_from_excel(db, body.year, body.names, _user(request))
    )
    return FromExcelOut(templates=made, entries=entries, linked=linked)
