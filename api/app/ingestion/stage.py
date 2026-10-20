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
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingestion.detect import read_pages
from app.ingestion.parsers import PARSERS
from app.ingestion.parsers.base import Check, Line, ParsedStatement, ParseError
from app.ingestion.storage import StatementStore
from app.models import (
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
    rules: list[rule_engine.Rule],
    patterns: dict[int, str],
    by_path: dict[str, Category],
    by_id: dict[int, Category],
) -> _Classified:
    if line.section in SECTION_PATHS:
        cat = by_path.get(SECTION_PATHS[line.section])
        type_ = {"payment": "transfer", "interest": "fee_interest", "fee": "fee_interest"}[
            line.section
        ]
        return _Classified(type_, cat.category_id if cat else None, None, None)

    default = "refund" if line.amount > 0 else "expense"
    hit = rule_engine.first_match(rules, line.description)
    if hit is None:
        return _Classified(default, None, None, None)
    kind = by_id[hit.category_id].kind
    type_ = {"transfer": "transfer", "income": "income", "savings": "savings"}.get(kind, default)
    return _Classified(type_, hit.category_id, hit.rule_id, patterns[hit.rule_id].strip(" *"))


def _continuity(db: Session, sf: StatementFile, parsed: ParsedStatement) -> Check | None:
    if parsed.opening_balance is None or not sf.accounts:
        return None
    account_ids = [a.account_id for a in sf.accounts]
    prev = db.scalar(
        select(StatementHeader)
        .join(
            StatementFileAccount,
            StatementFileAccount.statement_file_id == StatementHeader.statement_file_id,
        )
        .where(
            StatementFileAccount.account_id.in_(account_ids),
            StatementHeader.statement_file_id != sf.statement_file_id,
            StatementHeader.period_end < parsed.period_start,
        )
        .order_by(StatementHeader.period_end.desc())
        .limit(1)
    )
    if prev is None or prev.closing_balance is None:
        return None
    return Check(
        f"Opening balance = closing balance of the {prev.period_end:%b %d, %Y} statement",
        prev.closing_balance,
        parsed.opening_balance,
    )


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
        raise StageError(f"Reading {sf.source} statements is not built yet.", 422)
    if len(sf.accounts) != 1:
        raise StageError("Choose the statement's account first.", 422)
    account = sf.accounts[0]

    try:
        parsed = parser(read_pages(store.get(sf.blob_key)))
    except ParseError as exc:
        raise StageError(f"The statement could not be read: {exc}", 422) from exc

    _clear_preview(db, sf)
    db.add(
        StatementHeader(
            statement_file_id=sf.statement_file_id,
            parser=parsed.parser,
            period_start=parsed.period_start,
            period_end=parsed.period_end,
            opening_balance=parsed.opening_balance,
            closing_balance=parsed.closing_balance,
            totals_json=json.dumps({k: str(v) for k, v in parsed.totals.items()}),
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
    if (cont := _continuity(db, sf, parsed)) is not None:
        parsed.checks.append(cont)

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
    rules = [
        rule_engine.Rule(r.rule_id, r.pattern, r.match_type, r.category_id, r.priority, r.is_active)
        for r in rows
    ]
    patterns = {r.rule_id: r.pattern for r in rows}
    by_path, by_id = _paths(db)

    seen: Counter[tuple[date, Decimal, str]] = Counter()
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
                }
            ),
        )
        db.add(raw)
        db.flush()
        ident = (line.txn_date, line.amount, rule_engine.normalize(line.description))
        seen[ident] += 1
        c = _classify(line, rules, patterns, by_path, by_id)
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
                person=line.person,
                country=country,
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
                    person=s.person,
                    country=s.country,
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
