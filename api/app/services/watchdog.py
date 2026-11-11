"""The arrival watchdog (ADR-078): the app notices when data stops arriving.

- **Heartbeat.** The Gmail script (ADR-020) checks in on every run (`GET /api/inbox?alerts=true`).
  The time is kept in core.app_setting; more than SILENT_DAYS without one and the script has
  probably stopped (an expired authorization, a removed trigger), so nothing by email arrives.
- **Alerts.** What a person should hear about without opening the app: a statement that is late
  (ADR-072). Each is emailed once, by the script, from Hernan's own Gmail (as the weekly digest,
  ADR-038: no mail service). The script's own silence can't be emailed by the script; it shows on
  Home and Data Status, and in Claude's daily check.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services import status as status_service

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
    state: str  # ok, silent, never
    last_seen: datetime | None
    note: str


def script(db: Session, now: datetime | None = None) -> Script:
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
    key: str
    title: str
    text: str


def alerts(db: Session, today: date | None = None) -> list[Alert]:
    """Everything worth an email today, whether or not it was already sent."""
    st = status_service.month_status(db, today, with_loads=False)
    out = []
    for s in st.sources:
        if s.state != "late":
            continue
        when = s.expected.isoformat() if s.expected else "x"
        out.append(Alert(f"late:{s.account_id}:{when}", f"{s.name}: statement is late", s.note))
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
