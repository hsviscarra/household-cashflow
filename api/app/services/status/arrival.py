"""How each account's data arrives (bank sync, email, a file you download) and what is next."""

from datetime import date, timedelta

from app.models import (
    Account,
)
from app.services.status.base import AccountTimeline, Source

# Banks whose statements reach Gmail and the Apps Script posts them (ADR-020).
EMAILED = ("PICHINCHA", "PACIFICARD", "DINERS")
EMAIL_LAG = 7  # days after a statement closes by which its email has usually arrived


def how_it_arrives(a: Account) -> str:
    """How an account's data gets in: bank sync, email or upload."""
    if a.sync_id:
        return "bank_sync"
    text = f"{a.institution} {a.name}".upper()
    return "email" if any(e in text for e in EMAILED) else "upload"


def _short(d: date) -> str:
    return f"{d:%b} {d.day}"


def sources(
    accounts: list[Account],
    timeline: list[AccountTimeline],
    waiting: dict[int, list[tuple[date, date, str]]],
    today: date,
) -> list[Source]:
    """Every open account: how its data arrives, the last day it covers, and whether the next
    piece is on its way, late, or waiting on a person."""
    lines = {t.account_id: t for t in timeline}
    out = []
    for a in accounts:
        if a.closed_on is not None and a.closed_on < today - timedelta(days=45):
            continue
        t = lines.get(a.account_id)
        if t is None:
            continue
        how = how_it_arrives(a)
        last = max((x.end for x in t.statements if x.state in ("loaded", "synced")), default=None)
        open_gaps = [g for g in t.gaps if g.start <= today]
        on_import = [
            w
            for w_start, w_end, w in waiting.get(a.account_id, [])
            for g in open_gaps
            if w_start <= g.end and w_end >= g.start
        ]
        closes = sorted(c for g in open_gaps for c in g.closes if c < today)
        if not open_gaps or (how == "bank_sync" and last is not None and last >= today):
            src = Source(a.account_id, a.name, how, last, "up_to_date", "Nothing to do")
        elif on_import:
            src = Source(
                a.account_id,
                a.name,
                how,
                last,
                "on_import",
                f"On Import, {on_import[0]}: open it and approve",
            )
        elif how == "bank_sync":
            src = Source(
                a.account_id,
                a.name,
                how,
                last,
                "late",
                f"Bank sync hasn't run since {_short(last)}" if last else "Bank sync hasn't run",
            )
        elif not closes:
            due = next((g.due for g in open_gaps if g.due), None)
            src = Source(
                a.account_id,
                a.name,
                how,
                last,
                "on_its_way",
                f"The bank issues it around {_short(due)}" if due else "Not issued yet",
                due,
            )
        elif how == "email":
            by = closes[0] + timedelta(days=EMAIL_LAG)
            if by >= today:
                src = Source(
                    a.account_id,
                    a.name,
                    how,
                    last,
                    "on_its_way",
                    f"Closed {_short(closes[0])}; its email usually arrives by {_short(by)}",
                    by,
                )
            else:
                src = Source(
                    a.account_id,
                    a.name,
                    how,
                    last,
                    "late",
                    f"Closed {_short(closes[0])} and hasn't arrived: check the Gmail script,"
                    " or upload it on Import",
                    by,
                )
        else:
            src = Source(
                a.account_id,
                a.name,
                how,
                last,
                "you_upload",
                f"Download the statement closing {_short(closes[0])} and upload it on Import",
                closes[0],
            )
        out.append(src)
    order = {"late": 0, "you_upload": 1, "on_import": 2, "on_its_way": 3, "up_to_date": 4}
    return sorted(out, key=lambda x: (order[x.state], x.name))
