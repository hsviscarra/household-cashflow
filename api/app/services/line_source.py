"""Where a line came from (ADR-034): everything the statement says about it, so a person can tell
what it was before choosing a category. The statement's text around the line is read from the
stored PDF on request and never saved; long digit runs (account numbers, cédulas) are masked to
their last four digits before they leave the server."""

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.detect import PdfError, read_pages
from app.ingestion.storage import StatementStore
from app.models import (
    Account,
    Counterparty,
    RawLine,
    StatementFile,
    StgTransaction,
    Transaction,
    TransferNote,
)
from app.services.classify import merchant_key

log = logging.getLogger(__name__)
AROUND = 3  # lines of the statement shown before and after
SIMILAR = 5  # earlier categorized lines of the same merchant
_DIGITS = re.compile(r"(?<![\d.,])\d[\d-]{4,}\d(?![.,]?\d)")


def mask(text: str) -> str:
    """'CTA 2201234567 CI 1712345678' -> 'CTA ••••4567 CI ••••5678': six or more digits keep
    only their last four, so no full account or ID number is shown."""

    def hide(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return m.group(0) if len(digits) < 6 else f"••••{digits[-4:]}"

    return _DIGITS.sub(hide, text)


@dataclass
class TextLine:
    line_no: int
    text: str
    is_line: bool


@dataclass
class Similar:
    txn_date: date
    amount: Decimal
    description: str
    category_id: int | None


@dataclass
class Source:
    transaction_id: int
    txn_date: date
    post_date: date | None
    amount: Decimal
    description: str
    account_name: str | None
    account_last4: str | None
    person: str | None
    pay_reference: str | None
    notes: str | None
    statement_file_id: int | None = None
    file_name: str | None = None
    bank: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    page: int | None = None
    line_no: int | None = None
    section: str | None = None
    cardholder: str | None = None
    text: str | None = None
    around: list[TextLine] = field(default_factory=list)
    note_from: str | None = None  # the name the bank printed in the transfer email
    note_person: str | None = None
    note: str | None = None
    similar: list[Similar] = field(default_factory=list)
    unreadable: bool = False


def _around(store: StatementStore, sf: StatementFile, raw: RawLine) -> tuple[list[TextLine], bool]:
    try:
        pages = read_pages(store.get(sf.blob_key))
    except (PdfError, OSError, KeyError, ValueError):
        return [], True
    except Exception:  # Azure's not-found and auth errors: the facts still show
        log.warning("Statement %s could not be read for a line's context", sf.statement_file_id)
        return [], True
    if not 1 <= raw.page <= len(pages):
        return [], False
    lines = pages[raw.page - 1].splitlines()
    lo, hi = max(1, raw.line_no - AROUND), min(len(lines), raw.line_no + AROUND)
    return [TextLine(n, mask(lines[n - 1]), n == raw.line_no) for n in range(lo, hi + 1)], False


def _fill_statement(db: Session, store: StatementStore, out: Source, raw_line_id: int) -> None:
    raw = db.get(RawLine, raw_line_id)
    if raw is None:
        return
    sf = db.get(StatementFile, raw.statement_file_id)
    out.page, out.line_no, out.section = raw.page, raw.line_no, raw.section
    out.cardholder, out.text = raw.cardholder, mask(raw.text)
    if sf is not None:
        out.statement_file_id, out.file_name, out.bank = (
            sf.statement_file_id,
            sf.file_name,
            sf.source,
        )
        out.period_start, out.period_end = sf.period_start, sf.period_end
        out.around, out.unreadable = _around(store, sf, raw)


def _similar(db: Session, description: str, not_id: int) -> list[Similar]:
    key = merchant_key(description)
    first_word = key.split(" ")[0] if key else ""
    if not first_word:
        return []
    rows = db.scalars(
        select(Transaction)
        .where(
            Transaction.category_id.is_not(None),
            Transaction.transaction_id != not_id,
            Transaction.description_raw.contains(first_word, autoescape=True),
        )
        .order_by(Transaction.txn_date.desc())
        .limit(200)
    )
    same = [t for t in rows if merchant_key(t.description_raw) == key][:SIMILAR]
    return [Similar(t.txn_date, t.amount, t.description_raw, t.category_id) for t in same]


def of_transaction(db: Session, store: StatementStore, t: Transaction) -> Source:
    account = db.get(Account, t.account_id) if t.account_id else None
    out = Source(
        t.transaction_id,
        t.txn_date,
        t.post_date,
        t.amount,
        t.description_raw,
        account.name if account else None,
        account.last4 if account else None,
        t.person,
        t.pay_reference,
        t.notes,
    )
    if t.raw_line_id:
        _fill_statement(db, store, out, t.raw_line_id)
    note = db.scalars(
        select(TransferNote).where(TransferNote.transaction_id == t.transaction_id)
    ).first()
    if note is not None:
        out.note_from = note.other_party
        out.note = note.description
        if note.counterparty_id:
            person = db.get(Counterparty, note.counterparty_id)
            out.note_person = person.name if person else None
    out.similar = _similar(db, t.description_raw, t.transaction_id)
    return out


def of_staged(db: Session, store: StatementStore, s: StgTransaction) -> Source:
    account = db.get(Account, s.account_id)
    out = Source(
        s.stg_id,
        s.txn_date,
        s.post_date,
        s.amount,
        s.description_raw,
        account.name if account else None,
        account.last4 if account else None,
        s.person,
        s.pay_reference,
        None,
    )
    _fill_statement(db, store, out, s.raw_line_id)
    out.similar = _similar(db, s.description_raw, -1)
    return out
