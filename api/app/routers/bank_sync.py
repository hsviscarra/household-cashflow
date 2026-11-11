"""Bank sync through SimpleFIN (ADR-044)."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.models import Account, Transaction
from app.services import bank_sync, inbox, invoices, people, recurring, transfers

router = APIRouter(prefix="/api/bank-sync", tags=["bank sync"])
DB = Annotated[Session, Depends(get_session)]
BY_HAND = timedelta(minutes=30)  # "Sync now" no more often than this, to respect the quota


class LinkIn(BaseModel):
    sync_id: str = Field(min_length=1, max_length=100)
    account_id: int | None = None


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


def _status(db: Session) -> dict[str, Any]:
    last = bank_sync.last_run(db)
    summary = json.loads(last.summary) if last else None
    pending = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.source == bank_sync.SOURCE)
    )
    # Read in full now: SQL Server allows one open result per connection (no MARS).
    accounts = list(
        db.scalars(
            select(Account).where(Account.is_active).order_by(Account.institution, Account.name)
        )
    )
    return {
        "configured": bank_sync.configured(),
        "due": bank_sync.due(db),
        "last_run": None
        if last is None
        else {"at": last.loaded_at.isoformat(), "by": last.loaded_by, **(summary or {})},
        "pending_lines": pending or 0,
        "accounts": [
            {
                "account_id": a.account_id,
                "name": a.name,
                "institution": a.institution,
                "sync_id": a.sync_id,
            }
            for a in accounts
        ],
    }


@router.get("")
def status(db: DB) -> dict[str, Any]:
    """Whether sync is set up, the last run (accounts SimpleFIN reaches, names and balances
    only), how many synced lines wait for their statement, and the app's accounts to link."""
    return _status(db)


@router.post("/run")
def run(
    db: DB,
    request: Request,
    auto: bool = False,
    today: Annotated[date | None, Query(include_in_schema=False)] = None,
) -> dict[str, Any]:
    """Read new movements. With auto (the app does this when it opens) it runs only when the
    last run is 12 hours old; by hand, every 30 minutes at most."""
    if auto and not bank_sync.configured():
        return {"ran": False, **_status(db)}
    if not bank_sync.configured():
        raise HTTPException(409, "Bank sync isn't set up; run infra/azure/setup-simplefin.sh.")
    last = bank_sync.last_run(db)
    now = datetime.now(UTC).replace(tzinfo=None)
    if auto and not bank_sync.due(db, now):
        return {"ran": False, **_status(db)}
    # By hand: every 30 minutes, or right away after linking an account the last run skipped.
    soon = last is not None and now - last.loaded_at < BY_HAND
    if not auto and soon and not bank_sync.newly_linked(db, last):
        raise HTTPException(429, "Synced a few minutes ago; try again in half an hour.")
    user = _user(request)
    try:
        result = bank_sync.sync(db, user, today)
    except bank_sync.SyncError as e:
        raise HTTPException(e.status, str(e)) from None
    if result.added:
        # The same follow-ups as an approved statement: people, transfers, recurring bills.
        people.tag_lines(db, user)
        transfers.match(db, user)
        invoices.link_pending(db, since=(today or date.today()) - timedelta(days=60))  # ADR-066
        months = db.scalars(
            select(Transaction.cash_month).where(Transaction.source == bank_sync.SOURCE).distinct()
        )
        for month in sorted(set(months)):
            recurring.match(db, month, user)
        # ADR-077: Claude categorizes what no rule knew, as after an approved statement.
        done = inbox.autopilot(db, user)
        return {
            "ran": True,
            "added": result.added,
            "auto": {"merchants": done.merchants, "lines": done.lines},
            **_status(db),
        }
    return {"ran": True, "added": result.added, **_status(db)}


@router.put("/link")
def link(body: LinkIn, db: DB) -> dict[str, Any]:
    """Link a SimpleFIN account to an app account (or unlink with account_id null)."""
    for a in db.scalars(select(Account).where(Account.sync_id == body.sync_id)):
        a.sync_id = None
    db.flush()  # free the id before giving it to another account (unique when set)
    if body.account_id is not None:
        account = db.get(Account, body.account_id)
        if account is None:
            raise HTTPException(404, "Account not found.")
        account.sync_id = body.sync_id
    db.commit()
    return _status(db)
