"""What the import preview shows for a batch (F4)."""

import json
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.upload import to_out
from app.models import (
    Account,
    Category,
    ImportBatch,
    RawLine,
    RejectedLine,
    StatementFile,
    StatementHeader,
    StgTransaction,
)
from app.schemas import (
    BatchOut,
    BatchRef,
    CategoryTotalOut,
    CheckOut,
    RejectOut,
    StgLineOut,
)


def category_paths(db: Session) -> dict[int, str]:
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    out: dict[int, str] = {}
    for cid, c in cats.items():
        parent = cats.get(c.parent_id) if c.parent_id is not None else None
        out[cid] = f"{parent.name} / {c.name}" if parent else c.name
    return out


def latest_batches(db: Session) -> dict[int, BatchRef]:
    out: dict[int, BatchRef] = {}
    for b in db.scalars(select(ImportBatch).order_by(ImportBatch.batch_id)):
        if b.status == "rejected" and b.statement_file_id in out:
            continue
        out[b.statement_file_id] = BatchRef(
            batch_id=b.batch_id, status=b.status, tieout_ok=b.tieout_ok
        )
    return out


def batch_out(db: Session, batch: ImportBatch) -> BatchOut:
    sf = db.get(StatementFile, batch.statement_file_id)
    header = db.get(StatementHeader, batch.statement_file_id)
    assert sf is not None and header is not None
    paths = category_paths(db)
    rows = db.execute(
        select(StgTransaction, RawLine.cardholder, Account.name)
        .join(RawLine, RawLine.raw_line_id == StgTransaction.raw_line_id)
        .join(Account, Account.account_id == StgTransaction.account_id)
        .where(StgTransaction.batch_id == batch.batch_id)
        .order_by(StgTransaction.txn_date, StgTransaction.stg_id)
    ).all()

    lines: list[StgLineOut] = []
    totals: dict[tuple[str, str], list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for s, cardholder, account_name in rows:
        path = paths.get(s.category_id) if s.category_id else None
        lines.append(
            StgLineOut(
                stg_id=s.stg_id,
                txn_date=s.txn_date,
                post_date=s.post_date,
                description=s.description_raw,
                merchant=s.merchant,
                amount=s.amount,
                type=s.type,
                category_id=s.category_id,
                category_path=path,
                person=s.person,
                country=s.country,
                cardholder=cardholder,
                account_name=account_name,
                pay_reference=s.pay_reference,
                is_duplicate=s.is_duplicate,
            )
        )
        if not s.is_duplicate:
            t = totals[(path or "Needs a category", s.type)]
            t[0] += 1
            t[1] += s.amount

    rejects = db.scalars(
        select(RejectedLine).where(RejectedLine.statement_file_id == sf.statement_file_id)
    )
    return BatchOut(
        batch_id=batch.batch_id,
        status=batch.status,
        tieout_ok=batch.tieout_ok,
        statement=to_out(
            sf, BatchRef(batch_id=batch.batch_id, status=batch.status, tieout_ok=batch.tieout_ok)
        ),
        period_start=header.period_start,
        period_end=header.period_end,
        opening_balance=header.opening_balance,
        closing_balance=header.closing_balance,
        checks=[CheckOut(**c) for c in json.loads(batch.checks_json)],
        lines=lines,
        by_category=sorted(
            (
                CategoryTotalOut(category_path=k[0], type=k[1], lines=int(v[0]), amount=v[1])
                for k, v in totals.items()
            ),
            key=lambda c: c.amount,
        ),
        rejects=[
            RejectOut(page=r.page, line_no=r.line_no, text=r.text, reason=r.reason) for r in rejects
        ],
        new_lines=sum(1 for ln in lines if not ln.is_duplicate),
        duplicate_lines=sum(1 for ln in lines if ln.is_duplicate),
        uncategorized=sum(1 for ln in lines if ln.category_id is None and not ln.is_duplicate),
        created_by=batch.created_by,
        decided_by=batch.decided_by,
        decided_at=batch.decided_at,
    )
