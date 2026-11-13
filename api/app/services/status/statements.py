"""Statements over time: what is approved, what waits on Import, what the bank sync covers,
and each account's timeline with its gaps."""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    ImportBatch,
    LoadLog,
    StatementFile,
    StatementFileAccount,
    StatementHeader,
    Transaction,
)
from app.services import bank_sync, recurring
from app.services.status.base import DAY, AccountTimeline, Gap, TimelineStatement, month_end


@dataclass
class _Stmt:
    file_id: int
    file_name: str
    account_id: int
    start: date
    end: date
    opening: Decimal | None
    closing: Decimal | None


def approved_statements(db: Session) -> list[_Stmt]:
    """Every approved statement with its account, period and balances."""
    approved = set(
        db.scalars(select(ImportBatch.statement_file_id).where(ImportBatch.status == "approved"))
    )
    if not approved:
        return []
    accounts = {a.account_id: a for a in db.scalars(select(Account))}
    files = {
        f.statement_file_id: f
        for f in db.scalars(
            select(StatementFile).where(StatementFile.statement_file_id.in_(approved))
        )
    }
    links: dict[int, list[int]] = defaultdict(list)
    for fa in db.scalars(
        select(StatementFileAccount).where(StatementFileAccount.statement_file_id.in_(approved))
    ):
        links[fa.statement_file_id].append(fa.account_id)
    out = []
    for h in db.scalars(
        select(StatementHeader).where(StatementHeader.statement_file_id.in_(approved))
    ):
        balances = json.loads(h.totals_json).get("balances", {})
        ids = links[h.statement_file_id]
        for account_id in ids:
            account = accounts[account_id]
            opening: Decimal | None
            closing: Decimal | None
            if len(ids) > 1 and account.last4 in balances:
                pair = balances[account.last4]
                opening, closing = Decimal(pair[0]), Decimal(pair[1])
            else:
                opening, closing = h.opening_balance, h.closing_balance
            out.append(
                _Stmt(
                    h.statement_file_id,
                    files[h.statement_file_id].file_name,
                    account_id,
                    h.period_start,
                    h.period_end,
                    opening,
                    closing,
                )
            )
    return sorted(out, key=lambda s: (s.account_id, s.start, s.file_id))


def not_loaded(db: Session) -> dict[int, list[tuple[date, date, str]]]:
    """Per account, statements uploaded but not approved yet: (start, end, where it stands).
    A month without an approved statement says so instead of "no statement" (Hernan uploaded a
    batch and saw every month unchanged: only approved statements count)."""
    latest: dict[int, str] = {}
    for b in db.scalars(select(ImportBatch).order_by(ImportBatch.batch_id)):
        latest[b.statement_file_id] = b.status
    out: dict[int, list[tuple[date, date, str]]] = defaultdict(list)
    rows = db.execute(
        select(StatementFile, StatementFileAccount.account_id).join(
            StatementFileAccount,
            StatementFileAccount.statement_file_id == StatementFile.statement_file_id,
        )
    )
    for sf, account_id in rows:
        state = latest.get(sf.statement_file_id)
        if state == "approved" or sf.period_start is None or sf.period_end is None:
            continue
        where = "waiting for approval" if state == "preview" else "uploaded, not read yet"
        out[account_id].append((sf.period_start, sf.period_end, where))
    return out


def next_cycle_end(end: date) -> date:
    """The same day a month later (clamped): when the statement after one ending on `end` ends."""
    m = recurring.add_months(end.replace(day=1), 1)
    last = (recurring.add_months(m, 1) - timedelta(days=1)).day
    if end == month_end(end):  # month-end statements (Produbanco): the next month's last day
        return m.replace(day=last)
    return m.replace(day=min(end.day, last))


SHOWN_BILLS = 4  # names spelled out in "N recurring items not paid yet"
SYNC_FRESH = 3  # days: a sync older than this no longer counts up to today


def _first_synced(db: Session, linked: set[int]) -> dict[int, date]:
    """The day of the first sync that reached each linked account (from the sync log)."""
    out: dict[int, date] = {}
    runs = db.scalars(
        select(LoadLog).where(LoadLog.source == "bank_sync").order_by(LoadLog.load_id)
    )
    for run in runs:
        try:
            seen = json.loads(run.summary).get("accounts") or []
        except (ValueError, AttributeError):
            continue  # an older log line without the account list
        for a in seen:
            aid = a.get("account_id") if isinstance(a, dict) else None
            if aid in linked:
                out.setdefault(aid, run.loaded_at.date())
        if len(out) == len(linked):
            break
    return out


def sync_coverage(
    db: Session, accounts: list[Account], today: date
) -> dict[int, tuple[date, date]]:
    """The days bank sync covers for each linked account, up to the last sync (to today while
    the last sync is fresh). It starts where the first sync started asking: the bank was asked
    for every movement since then, so a day without one is covered, not missing (ADR-085). With
    no record of that, it starts at the first synced line."""
    linked = {a.account_id for a in accounts if a.sync_id}
    if not linked:
        return {}
    last = db.scalars(
        select(LoadLog)
        .where(LoadLog.source == "bank_sync")
        .order_by(LoadLog.load_id.desc())
        .limit(1)
    ).first()
    if last is None:
        return {}
    synced = last.loaded_at.date()
    end = today if (today - synced).days <= SYNC_FRESH else synced
    asked_from = {aid: day - bank_sync.LOOKBACK for aid, day in _first_synced(db, linked).items()}
    first_line: dict[int, date] = {
        aid: day
        for aid, day in db.execute(
            select(Transaction.account_id, func.min(Transaction.txn_date))
            .where(Transaction.account_id.in_(linked), Transaction.source == "bank_sync")
            .group_by(Transaction.account_id)
        )
        if aid is not None and day is not None
    }
    out: dict[int, tuple[date, date]] = {}
    for aid in linked:
        starts = [d for d in (asked_from.get(aid), first_line.get(aid)) if d is not None]
        if starts and min(starts) <= end:
            out[aid] = (min(starts), end)
    return out


def statement_files(db: Session) -> dict[int, list[TimelineStatement]]:
    """Every uploaded statement with a period, per linked account, and where it stands."""
    latest: dict[int, ImportBatch] = {}
    for b in db.scalars(select(ImportBatch).order_by(ImportBatch.batch_id)):
        latest[b.statement_file_id] = b
    out: dict[int, list[TimelineStatement]] = defaultdict(list)
    # The period the parser read, for files whose period upload couldn't read from the first
    # page (a Pacificard statement printing "hasta 2VOCT/2026").
    read = {
        h.statement_file_id: (h.period_start, h.period_end)
        for h in db.scalars(select(StatementHeader))
    }
    rows = db.execute(
        select(StatementFile, StatementFileAccount.account_id).join(
            StatementFileAccount,
            StatementFileAccount.statement_file_id == StatementFile.statement_file_id,
        )
    )
    for sf, account_id in list(rows):
        start, end = sf.period_start, sf.period_end
        if start is None or end is None:
            start, end = read.get(sf.statement_file_id, (None, None))
        if start is None or end is None:
            continue
        batch = latest.get(sf.statement_file_id)
        state = _standing(batch)
        out[account_id].append(
            TimelineStatement(
                sf.statement_file_id,
                sf.file_name,
                start,
                end,
                state,
                batch.batch_id if batch is not None and batch.status != "rejected" else None,
            )
        )
    for items in out.values():
        items.sort(key=lambda t: (t.start, t.end, t.file_id))
    return out


def _standing(batch: ImportBatch | None) -> str:
    if batch is None or batch.status == "rejected":
        return "not_read"
    if batch.status == "approved":
        return "loaded"
    return "waiting" if batch.tieout_ok else "problems"


def prev_cycle_end(end: date) -> date:
    """The same day a month earlier (clamped; month ends stay month ends)."""
    m = recurring.add_months(end.replace(day=1), -1)
    last = (end.replace(day=1) - timedelta(days=1)).day
    if end == month_end(end):
        return m.replace(day=last)
    return m.replace(day=min(end.day, last))


def statement_closes(
    gap_start: date, gap_end: date, before: date | None, after: date | None, issued_by: date
) -> list[date]:
    """The closing days of the statements that would fill a gap, from the statement right after
    it (each one closes the day before the next starts, a month apart) or the one right before
    it; only those already issued."""
    out: list[date] = []
    if after is not None:
        c = gap_end
        while c >= gap_start:
            out.append(c)
            c = prev_cycle_end(c)
    elif before is not None:
        c = next_cycle_end(before)
        while c <= issued_by:
            out.append(c)
            if c >= gap_end:
                break
            c = next_cycle_end(c)
    return sorted(out)


# How each bank names its statement file, where the name carries the closing date.
FILE_NAMES = {
    "Capital One": lambda close, last4: f"Statement_{close:%m%Y}_{last4}.pdf",
    "Bank of America": lambda close, last4: f"eStmt_{close:%Y-%m-%d}.pdf",
    "Pacificard": lambda close, last4: f"ESTADOCUENTA{close:%Y%m}.pdf",
}


def _file_names(a: Account, closes: list[date]) -> list[str]:
    name = FILE_NAMES.get(a.institution)
    return [name(c, a.last4 or "") for c in closes] if name else []


def timeline(
    accounts: list[Account],
    files: dict[int, list[TimelineStatement]],
    expected_from: date,
    today: date,
) -> list[AccountTimeline]:
    """Per account: its statements in order and the days no statement covers, from the first
    month Data Status checks up to today (or the day it closed). The last gap is the current
    cycle, not missing, while the bank hasn't issued its statement yet."""
    out = []
    for a in accounts:
        stmts = files.get(a.account_id, [])
        horizon = min(today, a.closed_on) if a.closed_on else today
        since = max(expected_from, a.opened_on) if a.opened_on else expected_from
        gaps = [Gap(s, e) for s, e in _gaps([(t.start, t.end) for t in stmts], since, horizon)]
        if stmts and gaps and gaps[-1].start > max(t.end for t in stmts):
            last_end = max(t.end for t in stmts)
            due = next_cycle_end(last_end)
            if due > horizon and not (a.closed_on and a.closed_on <= today):
                gaps[-1].due = due
        for g in gaps:
            if g.due:
                continue
            before = next((t.end for t in stmts if t.end == g.start - timedelta(days=1)), None)
            after = next((t.start for t in stmts if t.start == g.end + timedelta(days=1)), None)
            g.closes = statement_closes(g.start, g.end, before, after, today)
            g.files = _file_names(a, g.closes)
        days = Counter(t.start.day for t in stmts)
        out.append(
            AccountTimeline(
                a.account_id,
                a.name,
                a.closed_on,
                a.opened_on,
                days.most_common(1)[0][0] if days else None,
                stmts,
                gaps,
            )
        )
    return out


def _gaps(periods: list[tuple[date, date]], start: date, end: date) -> list[tuple[date, date]]:
    """The day ranges of start..end that no period covers."""
    gaps, cursor = [], start
    for p_start, p_end in sorted(periods):
        if p_end < cursor or p_start > end:
            continue
        if p_start > cursor:
            gaps.append((cursor, min(p_start - DAY, end)))
        cursor = max(cursor, p_end + DAY)
        if cursor > end:
            break
    if cursor <= end:
        gaps.append((cursor, end))
    return gaps
