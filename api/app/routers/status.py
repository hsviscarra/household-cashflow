"""Month status (F12, ADR-009): each month complete, or what is missing."""

from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ops.backup import BackupStore
from app.schemas import (
    AccountTimelineOut,
    BackupStatusOut,
    CoverageOut,
    GapOut,
    LoadOut,
    MonthStatusOut,
    ScriptOut,
    SourceOut,
    StatusAccountOut,
    StatusItemOut,
    StatusOut,
    TimelineStatementOut,
)
from app.services import backups, watchdog
from app.services import status as month_status
from app.services.backups import get_backup_store

router = APIRouter(prefix="/api", tags=["status"])
DB = Annotated[Session, Depends(get_session)]


@router.get("/status", response_model=StatusOut)
def get_status(
    db: DB,
    today: Annotated[date | None, Query(description="For tests: the day to check up to")] = None,
) -> StatusOut:
    s = month_status.month_status(db, today)
    return StatusOut(
        today=s.today,
        excel_through=s.excel_through,
        accounts=[
            StatusAccountOut(account_id=a.account_id, name=a.name, kind=a.kind, owner=a.owner)
            for a in s.accounts
        ],
        months=[
            MonthStatusOut(
                month=m.month,
                source=m.source,  # type: ignore[arg-type]
                complete=m.complete,
                items=[StatusItemOut(**vars(i)) for i in m.items],
                coverage=[
                    CoverageOut(
                        account_id=c.account_id,
                        state=c.state,  # type: ignore[arg-type]
                        covered_days=c.covered_days,
                        days=c.days,
                    )
                    for c in m.coverage
                ],
            )
            for m in s.months
        ],
        loads=[LoadOut(**vars(x)) for x in s.loads],
        statements=[
            AccountTimelineOut(
                account_id=t.account_id,
                name=t.name,
                closed_on=t.closed_on,
                opened_on=t.opened_on,
                start_day=t.start_day,
                statements=[
                    TimelineStatementOut(
                        statement_file_id=x.file_id,
                        file_name=x.file_name,
                        start=x.start,
                        end=x.end,
                        state=x.state,  # type: ignore[arg-type]
                        batch_id=x.batch_id,
                    )
                    for x in t.statements
                ],
                gaps=[
                    GapOut(start=g.start, end=g.end, due=g.due, closes=g.closes, files=g.files)
                    for g in t.gaps
                ],
            )
            for t in s.timeline
        ],
        sources=[SourceOut(**vars(x)) for x in s.sources],
        script=ScriptOut(**vars(watchdog.script(db))),
    )


@router.get("/backups", response_model=BackupStatusOut)
def backup_status(store: Annotated[BackupStore, Depends(get_backup_store)]) -> BackupStatusOut:
    """The latest backup and restore drill (F17), and whether either is overdue."""
    s = backups.status(store)
    return BackupStatusOut(**asdict(s))


class AlertKindOut(BaseModel):
    key: str
    label: str
    on: bool


class AlertSettingsOut(BaseModel):
    kinds: list[AlertKindOut]
    now: list[str]  # what would be emailed today, sent already or not


class AlertSettingsIn(BaseModel):
    off: list[str]


def _alert_settings(db: Session) -> AlertSettingsOut:
    skip = watchdog.off(db)
    return AlertSettingsOut(
        kinds=[AlertKindOut(key=k, label=v, on=k not in skip) for k, v in watchdog.KINDS.items()],
        now=[f"{a.title}. {a.text}".strip() for a in watchdog.alerts(db)],
    )


@router.get("/alerts", response_model=AlertSettingsOut)
def alert_settings(db: DB) -> AlertSettingsOut:
    """Which kinds of alert the daily email carries (ADR-082), and what it would say today."""
    return _alert_settings(db)


@router.put("/alerts", response_model=AlertSettingsOut)
def set_alert_settings(body: AlertSettingsIn, db: DB, request: Request) -> AlertSettingsOut:
    who = (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()
    watchdog.set_off(db, set(body.off), who)
    return _alert_settings(db)
