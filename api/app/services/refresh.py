"""Bringing new bank movements in, with everything that follows them (ADR-085).

One place for "sync, then settle what arrived", used by the app when it opens, by Sync now and
by the daily check-in, so the three can't drift apart: people, transfers, invoices, recurring
bills and Claude's categories run after every sync that added lines, as after an approved
statement."""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transaction
from app.services import bank_sync, inbox, invoices, people, recurring, transfers

log = logging.getLogger(__name__)
INVOICE_LINK_DAYS = 60  # how far back a new line may pay an invoice still waiting (ADR-066)


@dataclass
class Refreshed:
    added: int = 0
    merchants: int = 0  # merchants Claude categorized by itself (ADR-077)
    lines: int = 0
    errors: list[str] = field(default_factory=list)


def bank(db: Session, user: str, today: date | None = None) -> Refreshed:
    """Sync the linked accounts and, when lines arrived, run the follow-ups. Raises
    `bank_sync.SyncError` when the sync itself fails; the follow-ups never ask the network
    except Claude's categories, which leave everything in To do when they fail."""
    today = today or date.today()
    result = bank_sync.sync(db, user, today)
    out = Refreshed(added=result.added, errors=result.errors)
    if not result.added:
        return out
    people.tag_lines(db, user)
    transfers.match(db, user)
    invoices.link_pending(db, since=today - timedelta(days=INVOICE_LINK_DAYS))
    months = db.scalars(
        select(Transaction.cash_month).where(Transaction.source == bank_sync.SOURCE).distinct()
    )
    for month in sorted(set(months)):
        recurring.match(db, month, user)
    done = inbox.autopilot(db, user)
    out.merchants, out.lines = done.merchants, done.lines
    return out


def bank_if_due(db: Session, user: str, today: date | None = None) -> Refreshed | None:
    """The daily check-in's sync: only when one is due (set up, and the last one old enough).
    None when it didn't run or the bank didn't answer; a failed sync must not stop the alerts."""
    if not bank_sync.due(db):
        return None
    try:
        return bank(db, user, today)
    except bank_sync.SyncError as exc:
        log.warning("Daily bank sync failed: %s", exc)  # the watchdog reports a stale sync
        return None
