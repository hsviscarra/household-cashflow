"""From a stored statement to an approved load (F4).

parse_statement: read the PDF, parse it, keep raw lines and rejects, tie out, classify with the
merchant rules, flag duplicates, and leave everything in staging as a batch for preview.
approve: move the batch's new lines into core.transaction in one database transaction and log it.
Nothing reaches core until the statement ties out and Hernan approves.
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
from app.services import rules as rule_engine

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
    desc = rule_engine.normalize(line.description)
    raw = f"statement|{account_id}|{line.txn_date}|{line.amount}|{desc}|{occurrence}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class _Classified:
    type: str
    category_id: int | None
    rule_id: int | None
    merchant: str | None


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

    # Money in on a card is a refund; on a bank account it is income until a rule says otherwise.
    money_in = "refund" if account.kind == "credit_card" else "income"
    default = money_in if line.amount > 0 else "expense"
    hit = rule_engine.first_match(rules, line.description, line.amount)
    if hit is None:
        return _Classified(default, None, None, None)
    kind = by_id[hit.category_id].kind
    type_ = {"transfer": "transfer", "income": "income", "savings": "savings"}.get(kind, default)
    return _Classified(type_, hit.category_id, hit.rule_id, patterns[hit.rule_id].strip(" *"))


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


def parse_statement(
    db: Session, store: StatementStore, sf: StatementFile, user: str
) -> ImportBatch:
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

    # One statement may cover several accounts (BofA checking and savings), keyed by last four.
    accounts: dict[str | None, Account] = {}
    if parsed.balances:
        by_last4 = {a.last4: a for a in sf.accounts if a.last4}
        for last4 in parsed.balances:
            if last4 not in by_last4:
                raise StageError(
                    f"The statement covers account •••• {last4}, which is not linked to it. "
                    "Set its last four digits in Settings, then upload again.",
                    422,
                )
            accounts[last4] = by_last4[last4]
    elif len(sf.accounts) == 1:
        accounts[None] = sf.accounts[0]
    else:
        raise StageError("This statement is linked to several accounts; keep only one.", 422)

    _clear_preview(db, sf)
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
                person=line.person or account.owner,
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
    db.commit()
    db.refresh(batch)
    return batch


def approve(db: Session, batch: ImportBatch, user: str) -> tuple[int, int]:
    """Load the batch's new lines. Returns (loaded, skipped as already loaded)."""
    if batch.status != "preview":
        raise StageError(f"This batch is already {batch.status}.", 409)
    if not batch.tieout_ok:
        raise StageError("The statement does not tie out; it can't be loaded.", 409)

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
    try:
        for s in new:
            cat = cats.get(s.category_id) if s.category_id else None
            db.add(
                Transaction(
                    natural_key=s.natural_key,
                    account_id=s.account_id,
                    statement_file_id=batch.statement_file_id,
                    raw_line_id=s.raw_line_id,
                    import_batch_id=batch.batch_id,
                    txn_date=s.txn_date,
                    post_date=s.post_date,
                    cash_month=s.txn_date.replace(day=1),
                    amount=s.amount,
                    description_raw=s.description_raw,
                    merchant=s.merchant,
                    type=s.type,
                    category_id=s.category_id,
                    rule_id=s.rule_id,
                    category_source=(
                        "rule" if s.rule_id else ("section" if s.category_id else None)
                    ),
                    person=s.person,
                    country=s.country,
                    pay_reference=s.pay_reference,
                    is_fixed=bool(cat and cat.is_fixed),
                    source="statement",
                    status="confirmed",
                )
            )
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
                    }
                ),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(new), len(staged) - len(new)


def reject(db: Session, batch: ImportBatch, user: str) -> None:
    if batch.status != "preview":
        raise StageError(f"This batch is already {batch.status}.", 409)
    batch.status = "rejected"
    batch.decided_by = user
    batch.decided_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
