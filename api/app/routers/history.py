"""Excel history import and cash flow reads (F2)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.models import Budget, v_category_month, v_monthly_cash, v_monthly_cashflow
from app.schemas import (
    CategoryMonthOut,
    HistoryLoadOut,
    HistoryPreviewOut,
    MonthlyCashflowOut,
    PlanMonthOut,
)
from app.services import history_load, recurring
from app.services.excel_history import ParsedWorkbook, parse_workbook

router = APIRouter(prefix="/api", tags=["history"])
DB = Annotated[Session, Depends(get_session)]
MAX_BYTES = 10 * 1024 * 1024


async def _read(file: UploadFile) -> tuple[bytes, ParsedWorkbook]:
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(422, "Choose the Cash Flow workbook (.xlsx).")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The file is larger than 10 MB.")
    try:
        return data, parse_workbook(data)
    except (BadZipFile, KeyError, ValueError, OSError) as exc:
        raise HTTPException(422, "This file could not be read as an Excel workbook.") from exc


@router.post("/history/excel/preview", response_model=HistoryPreviewOut)
async def preview_history(file: UploadFile, db: DB) -> HistoryPreviewOut:
    data, parsed = await _read(file)
    return history_load.preview(db, parsed, file.filename or "", history_load.sha256(data))


@router.post("/history/excel/load", response_model=HistoryLoadOut)
async def load_history(file: UploadFile, request: Request, db: DB) -> HistoryLoadOut:
    data, parsed = await _read(file)
    user = (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()
    try:
        out = history_load.load(db, parsed, file.filename or "", history_load.sha256(data), user)
    except history_load.HistoryError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    # A reload replaces the history lines: link them to recurring entries again (F11).
    recurring.match_all(db, user)
    return out


@router.get("/cashflow/monthly", response_model=list[MonthlyCashflowOut])
def monthly_cashflow(
    db: DB,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    view: Annotated[
        Literal["spending", "cash"],
        Query(description="spending: card purchases when made; cash: bank money only (ADR-007)"),
    ] = "spending",
) -> list[MonthlyCashflowOut]:
    v = v_monthly_cash if view == "cash" else v_monthly_cashflow
    q = select(v).order_by(v.c.cash_month)
    if start:
        q = q.where(v.c.cash_month >= start)
    if end:
        q = q.where(v.c.cash_month <= end)
    return [MonthlyCashflowOut.model_validate(r._mapping) for r in db.execute(q)]


@router.get("/cashflow/categories", response_model=list[CategoryMonthOut])
def category_months(
    db: DB, year: Annotated[int, Query(ge=2000, le=2100)]
) -> list[CategoryMonthOut]:
    v = v_category_month
    q = (
        select(v)
        .where(v.c.cash_month >= date(year, 1, 1), v.c.cash_month <= date(year, 12, 1))
        .order_by(v.c.cash_month, v.c.group_name, v.c.category_name)
    )
    return [CategoryMonthOut.model_validate(r._mapping) for r in db.execute(q)]


@router.get("/cashflow/plan", response_model=list[PlanMonthOut])
def plan(db: DB) -> list[PlanMonthOut]:
    """Per month: the recurring entries' expected amounts when the month has any (F11),
    otherwise the workbook's plan."""
    entries = recurring.plan_by_month(db)
    rows = db.execute(
        select(Budget.month, Budget.type, func.sum(Budget.amount).label("amount"))
        .group_by(Budget.month, Budget.type)
        .order_by(Budget.month)
    )
    out: dict[date, PlanMonthOut] = {}
    for month, type_, amount in rows:
        item = out.setdefault(
            month, PlanMonthOut(month=month, income=Decimal(0), outflows=Decimal(0))
        )
        amt = Decimal(str(amount))
        if type_ == "income":
            item.income += amt
        else:
            item.outflows -= amt
    for month, (income, outflows) in entries.items():
        out[month] = PlanMonthOut(month=month, income=income, outflows=outflows)
    return sorted(out.values(), key=lambda p: p.month)
