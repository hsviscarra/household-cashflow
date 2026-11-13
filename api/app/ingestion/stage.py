"""From a stored statement to an approved load (F4).

parse_statement: read the PDF, parse it, keep raw lines and rejects, tie out, classify with the
merchant rules, flag duplicates, and leave everything in staging as a batch for preview.
approve: move the batch's new lines into core.transaction in one database transaction and log it.
Nothing reaches core until the statement ties out and Hernan approves.
"""

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion import ocr
from app.ingestion.detect import read_pages
from app.ingestion.parsers import OCR_SOURCES, PARSERS
from app.ingestion.parsers.base import Check, Line, ParsedStatement, ParseError
from app.ingestion.storage import StatementStore
from app.models import (
    Account,
    Category,
    ImportBatch,
    LoadLog,
    MerchantRule,
    RawLine,
    RejectedLine,
    StatementFile,
    StatementFileAccount,
    StatementHeader,
    StgTransaction,
    Transaction,
)
from app.services import (
    bank_sync,
    classify,
    inbox,
    invoices,
    payday,
    people,
    recurring,
    transfers,
)
from app.services import rules as rule_engine

log = logging.getLogger(__name__)

EC_PLACES = ("QUITO", "GUAYAQUIL", "ECUADOR", "RUMINAHUI", "CUMBAYA", "MEJIA", "PICHIN")
SECTION_PATHS = {
    "payment": "Transfers/Card Payment",
    "interest": "Financial Costs/Credit Card Interest",
    "fee": "Financial Costs/Bank Fees",
    "interest_earned": "Interest Earned",
}
SECTION_TYPES = {
    "payment": "transfer",
    "interest": "fee_interest",
    "fee": "fee_interest",
    "interest_earned": "income",
}


class StageError(Exception):
    """A statement can't be read or a batch can't change; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _paths(db: Session) -> tuple[dict[str, Category], dict[int, Category]]:
    cats = list(db.scalars(select(Category)))
    by_id = {c.category_id: c for c in cats}
    by_path: dict[str, Category] = {}
    for c in cats:
        parent = by_id.get(c.parent_id) if c.parent_id is not None else None
        by_path[f"{parent.name}/{c.name}" if parent else c.name] = c
    return by_path, by_id


def natural_key(account_id: int, line: Line, occurrence: int) -> str:
    """A line's identity for deduplication: account, date, amount, normalized description and its
    position among identical lines of the statement."""
    desc = rule_engine.normalize(line.description)
    raw = f"statement|{account_id}|{line.txn_date}|{line.amount}|{desc}|{occurrence}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class _Classified:
    type: str
    category_id: int | None
    rule_id: int | None
    merchant: str | None
    person: str | None = None  # a rule's person (ADR-042)


def _classify(
    line: Line,
    account: Account,
    rules: list[rule_engine.Rule],
    patterns: dict[int, str],
    by_path: dict[str, Category],
    by_id: dict[int, Category],
) -> _Classified:
    if line.section in SECTION_PATHS:
        cat = by_path.get(SECTION_PATHS[line.section])
        type_ = SECTION_TYPES[line.section]
        return _Classified(type_, cat.category_id if cat else None, None, None)

    hit = rule_engine.first_match(rules, line.description, line.amount)
    if hit is None:
        return _Classified(classify.rule_type("expense", account, line.amount), None, None, None)
    type_ = classify.rule_type(by_id[hit.category_id].kind, account, line.amount)
    return _Classified(type_, hit.category_id, hit.rule_id, hit.merchant(), hit.set_person)


def _account_at_bank(db: Session, sf: StatementFile, last4: str) -> Account | None:
    from app.ingestion.upload import INSTITUTIONS  # upload imports parsers; avoid a cycle

    institution = INSTITUTIONS.get(sf.source)
    return db.scalar(
        select(Account).where(
            Account.institution == institution,
            Account.last4 == last4,
            Account.is_active == True,  # noqa: E712 (SQL Server needs = 1)
        )
    )


def _balances(header: StatementHeader) -> dict[str, tuple[Decimal, Decimal]]:
    raw = json.loads(header.totals_json).get("balances", {})
    return {k: (Decimal(v[0]), Decimal(v[1])) for k, v in raw.items()}


def _continuity(
    db: Session, sf: StatementFile, parsed: ParsedStatement, accounts: dict[str | None, Account]
) -> list[Check]:
    """Each account's opening balance must equal its closing balance on the previous statement.

    Only an adjacent statement counts: when a month is missing, the balances can't be compared
    and the gap is left for the data status page (F12) instead of blocking a correct statement."""
    checks: list[Check] = []
    for last4, account in accounts.items():
        opening = parsed.balances[last4][0] if last4 else parsed.opening_balance
        if opening is None:
            continue
        prev = db.scalar(
            select(StatementHeader)
            .join(
                StatementFileAccount,
                StatementFileAccount.statement_file_id == StatementHeader.statement_file_id,
            )
            .where(
                StatementFileAccount.account_id == account.account_id,
                StatementHeader.statement_file_id != sf.statement_file_id,
                StatementHeader.period_start < parsed.period_start,
            )
            .order_by(StatementHeader.period_end.desc())
            .limit(1)
        )
        if prev is None or prev.period_end < parsed.period_start - timedelta(days=7):
            continue
        closing = _balances(prev).get(last4 or "", (None, prev.closing_balance))[1]
        if closing is None:
            continue
        label = f" {account.name}" if last4 else ""
        checks.append(
            Check(
                f"Opening balance{label} = closing balance of the {prev.period_end:%b %d, %Y} "
                "statement",
                closing,
                opening,
            )
        )
    return checks


def _clear_preview(db: Session, sf: StatementFile) -> None:
    batches = list(
        db.scalars(select(ImportBatch).where(ImportBatch.statement_file_id == sf.statement_file_id))
    )
    if any(b.status == "approved" for b in batches):
        raise StageError("This statement is already loaded.", 409)
    for b in batches:
        db.execute(delete(StgTransaction).where(StgTransaction.batch_id == b.batch_id))
        db.delete(b)
    db.execute(delete(RawLine).where(RawLine.statement_file_id == sf.statement_file_id))
    db.execute(delete(RejectedLine).where(RejectedLine.statement_file_id == sf.statement_file_id))
    db.execute(
        delete(StatementHeader).where(StatementHeader.statement_file_id == sf.statement_file_id)
    )
    db.flush()


def _account_again(db: Session, sf: StatementFile, text: str) -> None:
    """Reading again re-checks an account the app chose (not one Hernan picked): a fix to how
    accounts are found reaches statements already uploaded, which can't be uploaded again."""
    from app.ingestion.detect import detect
    from app.ingestion.upload import resolve_accounts

    res = resolve_accounts(db, detect(text))
    if res.accounts and {a.account_id for a in res.accounts} != {a.account_id for a in sf.accounts}:
        sf.accounts = res.accounts
        sf.account_match = res.match


def parse_statement(  # noqa: C901, PLR0915 - baseline, docs/refactors.md #15
    db: Session, store: StatementStore, sf: StatementFile, user: str
) -> ImportBatch:
    """Read a stored statement with its bank's parser into a batch in preview: raw lines, tie-out
    and continuity checks, normalized lines with proposed categories."""
    parser = PARSERS.get(sf.source)
    if parser is None:
        raise StageError("This statement's format isn't recognized, so it can't be read.", 422)
    if not sf.accounts:
        raise StageError("Choose the statement's account first.", 422)

    try:
        data = store.get(sf.blob_key)
        crop = OCR_SOURCES.get(sf.source)
        pages = ocr.ocr_pages(data, crop) if crop is not None else read_pages(data)
        if crop is None and not "".join(pages).strip() and ocr.available():
            pages = ocr.ocr_pages(data)  # a scan: no text layer, so read the page pictures
        parsed = parser(pages)
    except (ParseError, ocr.OcrError) as exc:
        raise StageError(f"The statement could not be read: {exc}", 422) from exc
    if sf.account_match != "manual" and not parsed.balances and crop is None:
        _account_again(db, sf, "\n".join(pages))

    # One statement may cover several accounts (BofA checking and savings), keyed by last four.
    accounts: dict[str | None, Account] = {}
    if parsed.balances:
        by_last4 = {a.last4: a for a in sf.accounts if a.last4}
        for last4 in parsed.balances:
            if last4 not in by_last4:
                # Linked only to some of its accounts when uploaded (BofA checking without its
                # savings): link the bank's active account with those digits now. Uploading again
                # can't do it, since the same file is refused as a duplicate.
                found = _account_at_bank(db, sf, last4)
                if found is None:
                    raise StageError(
                        f"The statement covers account •••• {last4}, which no active account has "
                        "as its last four digits. Set them in Settings → Accounts, then read the "
                        "statement again.",
                        422,
                    )
                sf.accounts.append(found)
                by_last4[last4] = found
            accounts[last4] = by_last4[last4]
    elif len(sf.accounts) == 1:
        accounts[None] = sf.accounts[0]
    else:
        raise StageError("This statement is linked to several accounts; keep only one.", 422)

    _clear_preview(db, sf)
    if sf.period_start is None or sf.period_end is None:  # upload couldn't read it; the parser did
        sf.period_start, sf.period_end = parsed.period_start, parsed.period_end
    db.add(
        StatementHeader(
            statement_file_id=sf.statement_file_id,
            parser=parsed.parser,
            period_start=parsed.period_start,
            period_end=parsed.period_end,
            opening_balance=parsed.opening_balance,
            closing_balance=parsed.closing_balance,
            totals_json=json.dumps(
                {
                    **{k: str(v) for k, v in parsed.totals.items()},
                    "balances": {k: [str(o), str(c)] for k, (o, c) in parsed.balances.items()},
                }
            ),
        )
    )
    for r in parsed.rejects:
        db.add(
            RejectedLine(
                statement_file_id=sf.statement_file_id,
                page=r.page,
                line_no=r.line_no,
                text=r.text[:400],
                reason=r.reason[:200],
            )
        )
    parsed.checks += _continuity(db, sf, parsed, accounts)

    batch = ImportBatch(
        statement_file_id=sf.statement_file_id,
        status="preview",
        tieout_ok=parsed.tieout_ok and all(c.ok for c in parsed.checks),
        checks_json=json.dumps(
            [
                {"name": c.name, "expected": str(c.expected), "actual": str(c.actual), "ok": c.ok}
                for c in parsed.checks
            ]
        ),
        created_by=user,
    )
    db.add(batch)
    db.flush()

    rows = list(db.scalars(select(MerchantRule)))
    rules = [rule_engine.Rule.of(r) for r in rows]
    patterns = {r.rule_id: r.pattern for r in rows}
    by_path, by_id = _paths(db)

    seen: Counter[tuple[int, date, Decimal, str]] = Counter()
    staged: list[StgTransaction] = []
    for line in parsed.lines:
        raw = RawLine(
            statement_file_id=sf.statement_file_id,
            page=line.page,
            line_no=line.line_no,
            section=line.section,
            cardholder=line.cardholder,
            text=line.text[:400],
            data_json=json.dumps(
                {
                    "txn_date": line.txn_date.isoformat(),
                    "post_date": line.post_date.isoformat() if line.post_date else None,
                    "amount": str(line.amount),
                    "description": line.description,
                    "account": line.account,
                    "reference": line.reference,
                }
            ),
        )
        db.add(raw)
        db.flush()
        account = accounts[line.account if parsed.balances else None]
        ident = (
            account.account_id,
            line.txn_date,
            line.amount,
            rule_engine.normalize(line.description),
        )
        seen[ident] += 1
        c = _classify(line, account, rules, patterns, by_path, by_id)
        upper = line.description.upper()
        country = "EC" if any(p in upper for p in EC_PLACES) else account.country
        staged.append(
            StgTransaction(
                batch_id=batch.batch_id,
                raw_line_id=raw.raw_line_id,
                account_id=account.account_id,
                natural_key=natural_key(account.account_id, line, seen[ident]),
                txn_date=line.txn_date,
                post_date=line.post_date,
                amount=line.amount,
                description_raw=line.description[:400],
                merchant=c.merchant,
                type=c.type,
                category_id=c.category_id,
                rule_id=c.rule_id,
                person=c.person or line.person or account.owner,
                country=country,
                pay_reference=line.reference,
                is_duplicate=False,
            )
        )
    keys = [s.natural_key for s in staged]
    existing = (
        set(db.scalars(select(Transaction.natural_key).where(Transaction.natural_key.in_(keys))))
        if keys
        else set()
    )
    for s in staged:
        s.is_duplicate = s.natural_key in existing
    db.add_all(staged)
    db.flush()
    # Transfer notes and people's texts: the category they'll give, shown in the preview.
    people.apply_preview(db, staged)
    db.commit()
    db.refresh(batch)
    return batch


def approve(db: Session, batch: ImportBatch, user: str) -> tuple[int, int]:
    """Load the batch's new lines. Returns (loaded, skipped as already loaded)."""
    if batch.status != "preview":
        raise StageError(f"This batch is already {batch.status}.", 409)
    if not batch.tieout_ok:
        raise StageError("The statement does not tie out; it can't be loaded.", 409)

    classify.classify_waiting(
        db, batch_id=batch.batch_id
    )  # rules saved since the statement was read
    staged = list(
        db.scalars(select(StgTransaction).where(StgTransaction.batch_id == batch.batch_id))
    )
    keys = [s.natural_key for s in staged]
    existing = (
        set(db.scalars(select(Transaction.natural_key).where(Transaction.natural_key.in_(keys))))
        if keys
        else set()
    )
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    new = [s for s in staged if s.natural_key not in existing]
    loaded: list[Transaction] = []
    try:
        for s in new:
            cat = cats.get(s.category_id) if s.category_id else None
            loaded.append(
                Transaction(
                    natural_key=s.natural_key,
                    account_id=s.account_id,
                    statement_file_id=batch.statement_file_id,
                    raw_line_id=s.raw_line_id,
                    import_batch_id=batch.batch_id,
                    txn_date=s.txn_date,
                    post_date=s.post_date,
                    cash_month=payday.cash_month(s.txn_date, s.description_raw, s.amount),
                    amount=s.amount,
                    description_raw=s.description_raw,
                    merchant=s.merchant,
                    type=s.type,
                    category_id=s.category_id,
                    rule_id=s.rule_id,
                    category_source=(
                        s.category_source
                        or ("rule" if s.rule_id else ("section" if s.category_id else None))
                    ),
                    person=s.person,
                    country=s.country,
                    pay_reference=s.pay_reference,
                    is_fixed=bool(cat and cat.is_fixed),
                    source="statement",
                    status="confirmed",
                )
            )
        db.add_all(loaded)
        db.flush()
        # Lines the bank sync brought before this statement give their place to it (ADR-044).
        absorbed = bank_sync.absorb(db, loaded, user)
        batch.status = "approved"
        batch.decided_by = user
        batch.decided_at = datetime.now(UTC).replace(tzinfo=None)
        sf = db.get(StatementFile, batch.statement_file_id)
        db.add(
            LoadLog(
                source="statement",
                file_sha256=sf.sha256 if sf else None,
                loaded_by=user,
                rows_loaded=len(new),
                summary=json.dumps(
                    {
                        "batch_id": batch.batch_id,
                        "statement_file_id": batch.statement_file_id,
                        "loaded": len(new),
                        "skipped_duplicates": len(staged) - len(new),
                        "bank_sync_matched": absorbed[0],
                        "bank_sync_removed": absorbed[1],
                    }
                ),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    # Transfer notes told before the statement, and people's names in descriptions (ADR-023).
    people.match_all(db, user)
    people.tag_lines(db, user)
    # The other side of a card payment or own-account transfer may already be loaded (F10).
    transfers.match(db, user)
    # Invoices that arrived before their statement: match them, and let their products decide
    # the category (ADR-066).
    if new:
        invoices.link_pending(db, since=min(s.txn_date for s in new) - timedelta(days=7))
    # New lines may pay a month's recurring entries (F11).
    for month in sorted({s.txn_date.replace(day=1) for s in new}):
        recurring.match(db, month, user)
    return len(new), len(staged) - len(new)


# ---------------------------------------------------------------- automatic approval
AUTO = " (automatic)"


def not_ready(db: Session, batch: ImportBatch) -> str | None:
    """Why a batch needs a person, or None when it can be approved on its own: it ties out
    (totals and the previous statement's closing balance) and no line was left unread."""
    if batch.status != "preview":
        return f"Already {batch.status}."
    if not batch.tieout_ok:
        return "It doesn't tie out."
    rejects = db.scalar(
        select(func.count())
        .select_from(RejectedLine)
        .where(RejectedLine.statement_file_id == batch.statement_file_id)
    )
    if rejects:
        return f"{rejects} {'line' if rejects == 1 else 'lines'} couldn't be read."
    return None


def auto_approve(db: Session, batch: ImportBatch, user: str) -> bool:
    """Approve a batch that needs nobody (and AUTO_APPROVE is on). Returns whether it did."""
    if not get_settings().auto_approve or not_ready(db, batch) is not None:
        return False
    approve(db, batch, user + AUTO)
    return True


def read_and_approve(
    sessions: Callable[[], Session], store: StatementStore, statement_id: int, user: str
) -> None:
    """In the background, after an upload or an emailed statement: read it into a batch and
    approve it when it ties out. Anything else waits on the Import page, where Read shows why."""
    with sessions() as db:
        sf = db.get(StatementFile, statement_id)
        if sf is None:
            return
        try:
            batch = parse_statement(db, store, sf, user)
            if auto_approve(db, batch, user):
                inbox.autopilot(db, user + AUTO)  # Claude's sure suggestions, ADR-029
        except StageError as exc:
            db.rollback()
            log.warning("Statement %s not read: %s", statement_id, exc)
        except Exception:  # a background task has nobody to answer: log it, keep the app up
            db.rollback()
            log.exception("Statement %s failed while reading", statement_id)


def reject(db: Session, batch: ImportBatch, user: str) -> None:
    """Mark a batch in preview as rejected; nothing reaches the approved lines."""
    if batch.status != "preview":
        raise StageError(f"This batch is already {batch.status}.", 409)
    batch.status = "rejected"
    batch.decided_by = user
    batch.decided_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
