"""Closing a month (ADR-087): one screen with only the exceptions.

From the CLOSE_DAY of the following month, the month just ended is ready to close: the daily
check-in writes its report and emails once. The screen gathers what other services already know
and nothing more: what keeps the month from being complete (Data status), what looks unusual
(groups well above their average), what the app decided on its own (rules saved from Claude's
sure suggestions), the invoices the month has, and the report. Closing records who and when in
`core.app_setting`; it locks nothing, and a closed month can be reopened.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AppSetting, Invoice
from app.services import inbox, projections, report, status
from app.services.recurring import add_months, first

log = logging.getLogger(__name__)

CENT = Decimal("0.01")
CLOSE_DAY = 3  # day of the next month from which a month is ready to close
CLOSED_KEY = "month-closed:"  # + YYYY-MM -> {"at": ..., "by": ...}
DECIDED_SLACK_DAYS = 10  # statements of a month keep arriving this long after it ends
MAX_BY = 120  # characters of who closed it (the setting holds 200 in all)
SYSTEM_USER = "gmail script"
SRI_URL = "https://srienlinea.sri.gob.ec"


class CloseError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Open:
    """Something that keeps the month from being complete, and where to settle it."""

    kind: str
    text: str
    link: str


@dataclass
class Unusual:
    group: str
    amount: Decimal
    average: Decimal


@dataclass
class Decided:
    rule_id: int
    pattern: str
    category_id: int
    lines: int
    is_active: bool


@dataclass
class Close:
    month: date
    ready_on: date
    ready: bool
    closed_at: datetime | None = None
    closed_by: str | None = None
    missing: list[Open] = field(default_factory=list)
    unusual: list[Unusual] = field(default_factory=list)
    decided: list[Decided] = field(default_factory=list)
    invoices: int = 0
    has_report: bool = False
    sri_url: str = SRI_URL


def last_month(today: date) -> date:
    return add_months(first(today), -1)


def ready_on(month: date) -> date:
    return add_months(first(month), 1).replace(day=CLOSE_DAY)


def _key(month: date) -> str:
    return f"{CLOSED_KEY}{month:%Y-%m}"


def _closed(db: Session, month: date) -> tuple[datetime | None, str | None]:
    row = db.get(AppSetting, _key(month))
    if row is None:
        return None, None
    try:
        saved = json.loads(row.setting_value)
        return datetime.fromisoformat(saved["at"]), str(saved["by"])
    except (ValueError, KeyError, TypeError):
        log.warning("Month close: unreadable record for %s", month)
        return None, None


def _missing(db: Session, month: date, today: date) -> list[Open]:
    st = next(
        (m for m in status.month_status(db, today, with_loads=False).months if m.month == month),
        None,
    )
    return [Open(i.kind, i.text, i.link) for i in st.items] if st else []


def _unusual(db: Session, month: date) -> list[Unusual]:
    # projections.alerts looks at the month before the day it is given.
    found = projections.alerts(db, add_months(month, 1))
    return [
        Unusual(a.group_name, a.amount.quantize(CENT), a.average.quantize(CENT))
        for a in found
        if a.group_name not in report.NOT_A_GROUP
    ]


def _decided(db: Session, month: date, today: date) -> list[Decided]:
    """Rules the app saved by itself while the month's lines were arriving."""
    start = datetime.combine(month, datetime.min.time())
    end = datetime.combine(add_months(month, 1), datetime.min.time()) + timedelta(
        days=DECIDED_SLACK_DAYS
    )
    days = (today - month).days + 1
    return [
        Decided(r.rule_id, r.pattern, r.category_id, r.lines, r.is_active)
        for r in inbox.recent_auto(db, days=days)
        if start <= r.accepted_at < end
    ]


def _invoices(db: Session, month: date) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.issue_date >= month, Invoice.issue_date < add_months(month, 1))
        )
        or 0
    )


def view(db: Session, month: date, today: date | None = None) -> Close:
    """Everything the Close screen shows for a month."""
    today = today or date.today()
    month = first(month)
    if month > first(today):
        raise CloseError("That month hasn't started yet.")
    at, by = _closed(db, month)
    due = ready_on(month)
    return Close(
        month=month,
        ready_on=due,
        ready=today >= due,
        closed_at=at,
        closed_by=by,
        missing=_missing(db, month, today),
        unusual=_unusual(db, month),
        decided=_decided(db, month, today),
        invoices=_invoices(db, month),
        has_report=report.get(db, month) is not None,
    )


def close(db: Session, month: date, user: str, today: date | None = None) -> Close:
    """Record the month as closed, writing its report first when it has none. A month with
    things still missing can be closed: the person has seen them on the screen."""
    today = today or date.today()
    month = first(month)
    if today < ready_on(month):
        raise CloseError(f"{month:%B} can be closed from {ready_on(month):%B} {CLOSE_DAY}.")
    if report.get(db, month) is None:
        try:
            report.generate(db, month, user, today)
        except report.ReportError as exc:
            raise CloseError(str(exc)) from exc
    value = json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "by": user[:MAX_BY]})
    row = db.get(AppSetting, _key(month))
    if row is None:
        db.add(AppSetting(setting_key=_key(month), setting_value=value, updated_by=user[:200]))
    else:
        row.setting_value, row.updated_by = value, user[:200]
    db.commit()
    return view(db, month, today)


def reopen(db: Session, month: date, today: date | None = None) -> Close:
    row = db.get(AppSetting, _key(first(month)))
    if row is not None:
        db.delete(row)
        db.commit()
    return view(db, month, today)


def prepare(db: Session, today: date | None = None) -> Close | None:
    """The daily check-in's part: from CLOSE_DAY, write last month's report if it has none and
    say the month is ready. None before that day, once it's closed, or with nothing loaded."""
    today = today or date.today()
    month = last_month(today)
    if today < ready_on(month) or _closed(db, month)[0] is not None:
        return None
    if report.get(db, month) is None:
        try:
            report.generate(db, month, SYSTEM_USER, today)
        except report.ReportError as exc:
            log.info("Month close: no report for %s yet (%s)", month, exc)
            return None
    return view(db, month, today)
