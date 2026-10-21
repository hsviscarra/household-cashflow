"""Store uploaded statement PDFs (F3): hash, de-duplicate, detect, keep the file, record it."""

import hashlib
from dataclasses import dataclass

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.ingestion import ocr
from app.ingestion.detect import SOURCES, Detection, PdfError, detect, read_pdf
from app.ingestion.parsers import PARSERS
from app.ingestion.storage import StatementStore
from app.models import Account, StatementFile
from app.schemas import BatchRef, StatementAccountOut, StatementOut, UploadResultOut

MAX_BYTES = 25 * 1024 * 1024
INSTITUTIONS = {
    "bofa": "Bank of America",
    "capitalone": "Capital One",
    "pichincha": "Banco Pichincha",
    "produbanco": "Produbanco",
    "diners": "Diners Club",
    "pacificard": "Pacificard",
}


@dataclass
class Resolution:
    accounts: list[Account]
    match: str | None


def resolve_accounts(db: Session, found: Detection) -> Resolution:
    """Last four digits first. Otherwise the bank's one account without last four digits on file,
    the one whose owner is the statement's main cardholder (Diners), or the bank's only account
    (a replacement card has new digits). Anything else is left for Hernan to pick."""
    institution = INSTITUTIONS.get(found.source)
    if institution is None:
        return Resolution([], None)
    at_bank = list(
        db.scalars(
            select(Account)
            .where(Account.institution == institution, Account.is_active == true())
            .order_by(Account.account_id)
        )
    )
    by_last4 = [a for a in at_bank if a.last4 and a.last4 in found.last4]
    if by_last4:
        return Resolution(by_last4, "last4")
    without_digits = [a for a in at_bank if not a.last4]
    if len(without_digits) == 1:
        return Resolution(without_digits, "by_bank")
    by_owner = [a for a in without_digits if found.owner and a.owner == found.owner]
    if len(by_owner) == 1:
        return Resolution(by_owner, "owner")
    if len(at_bank) == 1:
        return Resolution(at_bank, "by_bank")
    return Resolution([], None)


def to_out(sf: StatementFile, batch: BatchRef | None = None) -> StatementOut:
    return StatementOut(
        statement_file_id=sf.statement_file_id,
        file_name=sf.file_name,
        source=sf.source,
        source_label=SOURCES.get(sf.source, sf.source),
        status=sf.status,
        accounts=[StatementAccountOut.model_validate(a) for a in sf.accounts],
        account_match=sf.account_match,
        last4_found=[x for x in (sf.last4_found or "").split(",") if x],
        period_start=sf.period_start,
        period_end=sf.period_end,
        page_count=sf.page_count,
        size_bytes=sf.size_bytes,
        uploaded_by=sf.uploaded_by,
        uploaded_at=sf.uploaded_at,
        can_read=sf.source in PARSERS,
        batch=batch,
    )


def store_statement(
    db: Session, store: StatementStore, data: bytes, file_name: str, user: str
) -> UploadResultOut:
    name = (file_name or "statement.pdf")[:260]
    if len(data) > MAX_BYTES:
        return UploadResultOut(file_name=name, outcome="rejected", message="Larger than 25 MB.")
    if not data:
        return UploadResultOut(file_name=name, outcome="rejected", message="The file is empty.")

    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(StatementFile).where(StatementFile.sha256 == sha))
    if existing is not None:
        return UploadResultOut(
            file_name=name,
            outcome="duplicate",
            message=f"Already uploaded as {existing.file_name} on {existing.uploaded_at:%Y-%m-%d}.",
            statement=to_out(existing),
        )

    try:
        info = read_pdf(data)
    except PdfError as exc:
        return UploadResultOut(file_name=name, outcome="rejected", message=str(exc))

    text = info.text
    if not text.strip() and ocr.available():
        # A screenshot saved as PDF (Pacificard): read the header with OCR to recognize the bank.
        try:
            text = ocr.header_text(data)
        except ocr.OcrError:
            text = ""
    found = detect(text)
    res = resolve_accounts(db, found)
    status = (
        "unknown_format"
        if found.source == "unknown"
        else ("detected" if res.accounts else "needs_account")
    )
    key = f"{found.source}/{sha}.pdf"
    store.put(key, data)

    sf = StatementFile(
        sha256=sha,
        file_name=name,
        size_bytes=len(data),
        page_count=info.pages,
        source=found.source,
        status=status,
        last4_found=",".join(found.last4)[:60] or None,
        account_match=res.match,
        period_start=found.period_start,
        period_end=found.period_end,
        blob_key=key,
        uploaded_by=user,
        accounts=res.accounts,
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)

    message = {
        "detected": f"{found.label}: " + ", ".join(a.name for a in res.accounts) + ".",
        "needs_account": f"{found.label}, but which account? Choose it in the list below.",
        "unknown_format": "Format not recognized yet; kept for review.",
    }[status]
    return UploadResultOut(file_name=name, outcome="stored", message=message, statement=to_out(sf))
