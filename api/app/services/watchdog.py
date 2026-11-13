"""The arrival watchdog (ADR-078): the app notices when data stops arriving.

- **Heartbeat.** The Gmail script (ADR-020) checks in on every run (`GET /api/inbox?alerts=true`).
  The time is kept in core.app_setting; more than SILENT_DAYS without one and the script has
  probably stopped (an expired authorization, a removed trigger), so nothing by email arrives.
- **Alerts.** What a person should hear about without opening the app: a statement that is late
  (ADR-072). Each is emailed once, by the script, from Hernan's own Gmail (as the weekly digest,
  ADR-038: no mail service). The script's own silence can't be emailed by the script; it shows on
  Home and Data Status, and in Claude's daily check.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services import budget, digest, month_close, recurring, transfers
from app.services import status as status_service

log = logging.getLogger(__name__)

SEEN_KEY = "gmail-script:last-seen"
SENT_KEY = "alert-sent:"  # + the alert's key: the day it was emailed
SILENT_DAYS = 2
KEEP_SENT_DAYS = 120


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _put(db: Session, key: str, value: str, user: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(setting_key=key, setting_value=value, updated_by=user))
    else:
        row.setting_value, row.updated_by, row.updated_at = value, user, _now()


def check_in(db: Session, now: datetime | None = None) -> None:
    """The Gmail script ran."""
    _put(db, SEEN_KEY, (now or _now()).isoformat(timespec="seconds"), "gmail script")
    db.commit()


@dataclass
class Script:
    """A scheduled job's state and when it last ran."""

    state: str  # ok, silent, never
    last_seen: datetime | None
    note: str


def script(db: Session, now: datetime | None = None) -> Script:
    """Whether the Gmail script that forwards statements has checked in lately."""
    now = now or _now()
    row = db.get(AppSetting, SEEN_KEY)
    if row is None:
        return Script(
            "never",
            None,
            "The Gmail script hasn't checked in yet: paste the new Code.gs into it once "
            "(docs/runbooks/gmail-statements.md).",
        )
    seen = datetime.fromisoformat(row.setting_value)
    days = (now - seen).days
    if days >= SILENT_DAYS:
        return Script(
            "silent",
            seen,
            f"The Gmail script last checked in {days} days ago ({seen:%b} {seen.day}): "
            "statements by email aren't arriving. Open script.google.com, look at Executions, "
            "and run setup again if it asks for authorization.",
        )
    return Script("ok", seen, f"The Gmail script checked in {seen:%b} {seen.day}.")


@dataclass
class Alert:
    """Something a scheduled job needs attention for."""

    key: str
    title: str
    text: str


KINDS = {
    "late": "A statement is late",
    "unusual": "An unusual charge",
    "bill": "A bill is due in 3 days or late",
    "budget": "A budget reached 80% or went over",
    "transfer": "A large transfer has no other side",
    "close": "Last month is ready to close",
}
OFF_KEY = "alerts-off"  # kinds a person turned off, comma-separated (all on by default)
BILL_DAYS = 3
BUDGET_SHARE = Decimal("0.80")
TRANSFER_MIN = Decimal(500)
TRANSFER_DAYS = 10


def off(db: Session) -> set[str]:
    """The kinds of alert that are turned off."""
    row = db.get(AppSetting, OFF_KEY)
    return {k for k in (row.setting_value.split(",") if row else []) if k in KINDS}


def set_off(db: Session, kinds: set[str], user: str) -> set[str]:
    """Choose which kinds of alert are off; unknown kinds are dropped."""
    kinds = {k for k in kinds if k in KINDS}
    _put(db, OFF_KEY, ",".join(sorted(kinds)), user[:200])
    db.commit()
    return kinds


def _late(db: Session, today: date) -> list[Alert]:
    st = status_service.month_status(db, today, with_loads=False)
    out = []
    for s in st.sources:
        if s.state != "late":
            continue
        when = s.expected.isoformat() if s.expected else "x"
        out.append(Alert(f"late:{s.account_id}:{when}", f"{s.name}: statement is late", s.note))
    return out


def _unusual(db: Session, today: date) -> list[Alert]:
    out = []
    for i in digest._unusual(db, today):
        key = hashlib.sha1(i.text.encode()).hexdigest()[:20]
        out.append(Alert(f"unusual:{key}", "Unusual charge", i.text))
    return out


def _bills(db: Session, today: date) -> list[Alert]:
    month = today.replace(day=1)
    out = []
    for b in recurring.bills(db, month, today):
        if b.expected >= 0 or b.status not in ("due", "late") or b.due_day is None:
            continue
        days = b.due_day - today.day
        if b.status == "late":
            title, text = (
                f"{b.name} is late",
                f"It was due on day {b.due_day} and no payment is in.",
            )
        elif 0 <= days <= BILL_DAYS:
            when = "today" if days == 0 else f"in {days} {'day' if days == 1 else 'days'}"
            title, text = (
                f"{b.name} is due {when}",
                f"About {-b.expected:,.2f}, on day {b.due_day}.",
            )
        else:
            continue
        out.append(Alert(f"bill:{b.template_id}:{month:%Y-%m}:{b.status}", title, text))
    return out


def _budget(db: Session, today: date) -> list[Alert]:
    month = today.replace(day=1)
    out = []
    for g in budget.month_view(db, month, today).groups:
        if g.budget is None or g.available <= 0:
            continue
        if g.spent > g.available:
            level, words = "over", f"over its budget: {g.spent:,.2f} of {g.available:,.2f}"
        elif g.spent >= g.available * BUDGET_SHARE:
            level, words = (
                "80",
                f"at {g.spent / g.available:.0%} of its budget of {g.available:,.2f}",
            )
        else:
            continue
        out.append(Alert(f"budget:{g.group_id}:{month:%Y-%m}:{level}", f"{g.name} is {words}", ""))
    return out


def _transfers(db: Session, today: date) -> list[Alert]:
    out = []
    for t in transfers.unmatched(db):
        age = (today - t.txn_date).days
        if abs(t.amount) < TRANSFER_MIN or not TRANSFER_DAYS <= age <= 60:
            continue
        out.append(
            Alert(
                f"transfer:{t.transaction_id}",
                f"A transfer of {abs(t.amount):,.2f} has no other side",
                f"{t.description_raw} on {t.txn_date:%b} {t.txn_date.day}: pair it or say where "
                "it went on Transfers to settle.",
            )
        )
    return out[:5]


def _close(db: Session, today: date) -> list[Alert]:
    """From the 3rd, last month is ready to close (ADR-087); said once per month."""
    month = month_close.last_month(today)
    if today < month_close.ready_on(month):
        return []
    c = month_close.view(db, month, today)
    if c.closed_at is not None or not c.has_report:
        return []
    n = len(c.missing)
    what = "Nothing is missing." if not n else f"{n} thing{'' if n == 1 else 's'} still missing."
    return [
        Alert(
            f"close:{month:%Y-%m}",
            f"{month:%B} is ready to close",
            f"{what} Its report is written; open Close the month in the app.",
        )
    ]


FINDERS = {
    "late": _late,
    "unusual": _unusual,
    "bill": _bills,
    "budget": _budget,
    "transfer": _transfers,
    "close": _close,
}


def alerts(db: Session, today: date | None = None) -> list[Alert]:
    """Everything worth an email today, whether or not it was already sent: the kinds a person
    left on (ADR-082). One kind failing doesn't stop the others."""
    today = today or date.today()
    skip = off(db)
    out: list[Alert] = []
    for kind, find in FINDERS.items():
        if kind in skip:
            continue
        try:
            out += find(db, today)
        except Exception:
            db.rollback()
            log.exception("Alerts: %s failed", kind)
    return out


def fresh(db: Session, today: date | None = None, mark: bool = True) -> list[Alert]:
    """The alerts not emailed yet; with mark they count as sent from now on."""
    today = today or date.today()
    found = alerts(db, today)
    sent = {
        r.setting_key[len(SENT_KEY) :]: r
        for r in db.scalars(select(AppSetting).where(AppSetting.setting_key.like(f"{SENT_KEY}%")))
    }
    new = [a for a in found if a.key not in sent]
    if mark:
        for a in new:
            _put(db, SENT_KEY + a.key, today.isoformat(), "gmail script")
        old = (today - timedelta(days=KEEP_SENT_DAYS)).isoformat()
        for row in sent.values():
            if row.setting_value < old:
                db.delete(row)
        db.commit()
    return new
