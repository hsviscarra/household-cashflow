"""Monthly report and export (F16, ADR-015)."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.schemas import ExportDatasetOut, FindingOut, ReportMonthsOut, ReportOut
from app.services import export, report, suggest

router = APIRouter(prefix="/api", tags=["report"])
DB = Annotated[Session, Depends(get_session)]


def _run[T](fn: Callable[[], T]) -> T:
    try:
        return fn()
    except (report.ReportError, export.ExportError) as exc:
        raise HTTPException(exc.status, str(exc)) from exc


def _month(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m").date()
    except ValueError as exc:
        raise HTTPException(422, "Months look like 2026-10.") from exc


def _out(r: report.Report) -> ReportOut:
    return ReportOut(
        month=r.month,
        written_by=r.written_by,  # type: ignore[arg-type]
        model=r.model,
        generated_at=r.generated_at,
        generated_by=r.generated_by,
        facts=r.facts,
        findings=[FindingOut(**asdict(f)) for f in r.findings],
        notice=r.notice,
    )


@router.get("/reports", response_model=ReportMonthsOut)
def report_months(db: DB) -> ReportMonthsOut:
    return ReportMonthsOut(months=report.months(db), claude=suggest.available())


@router.get("/reports/{month}", response_model=ReportOut | None)
def get_report(month: str, db: DB) -> ReportOut | None:
    """The month's saved report, or null when it hasn't been generated."""
    r = report.get(db, _month(month))
    return _out(r) if r is not None else None


@router.post("/reports/{month}/generate", response_model=ReportOut)
def generate_report(
    month: str,
    request: Request,
    db: DB,
    today: Annotated[date | None, Query(description="Default today")] = None,
) -> ReportOut:
    user = (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()
    m = _month(month)
    return _out(_run(lambda: report.generate(db, m, user, today)))


@router.get("/exports", response_model=list[ExportDatasetOut])
def exports() -> list[ExportDatasetOut]:
    return [ExportDatasetOut(**asdict(d)) for d in export.DATASETS.values()]


@router.get("/exports/{key}.{fmt}")
def download(
    key: str,
    fmt: str,
    db: DB,
    month: Annotated[str | None, Query(description="2026-10")] = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> Response:
    m = _month(month) if month else None
    body, media, name = _run(lambda: export.render(db, key, fmt, m, year))
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
