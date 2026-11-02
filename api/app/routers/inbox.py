"""Statements by email (F20, ADR-020): the Gmail script posts each statement PDF here.

The script runs in Hernan's Gmail once a day, finds the banks' statement emails and posts their
PDF attachments with the inbox bearer token (checked in app.auth). Each file is stored exactly
like an upload (a file already uploaded is a duplicate, so posting it again is harmless), then,
when its bank and account are recognized, read into a batch that waits on the Import page for
approval. Nothing reaches the household's transactions without that approval.

Invoice XMLs (F21, ADR-021) come the same way: an XML attachment is read as an electronic
invoice, stored with its products and matched to the card line that paid it.
"""

import logging
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session, get_session_factory
from app.ingestion import ocr, stage
from app.ingestion.detect import PdfError, read_pdf
from app.ingestion.storage import StatementStore, get_store
from app.ingestion.upload import MAX_BYTES, store_statement
from app.models import StatementFile
from app.routers.invoices import receive_xml

router = APIRouter(prefix="/api/inbox", tags=["inbox"])
DB = Annotated[Session, Depends(get_session)]
Sessions = Annotated[Callable[[], Session], Depends(get_session_factory)]
log = logging.getLogger(__name__)
Store = Annotated[StatementStore, Depends(get_store)]


class InboxOut(BaseModel):
    file_name: str
    outcome: Literal["stored", "duplicate", "skipped", "rejected"]
    message: str
    statement_id: int | None = None
    # "read": a batch waits on the Import page, or an invoice was stored; "needs_attention":
    # stored, but it needs a person (an unknown format, an account to choose, or a statement that
    # couldn't be read); "skipped": an SRI document that isn't an invoice (a credit note).
    status: Literal["read", "needs_attention", "duplicate", "skipped", "rejected"]
    batch_id: int | None = None
    invoice_id: int | None = None


def _who(sender: str) -> str:
    sender = sender.strip()
    return f"gmail ({sender})"[:320] if sender else "gmail"


Status = Literal["read", "needs_attention", "duplicate", "skipped", "rejected"]
INVOICE_STATUS: dict[str, Status] = {
    "stored": "read",
    "duplicate": "duplicate",
    "skipped": "skipped",
    "rejected": "rejected",
}


def _is_xml(name: str, data: bytes) -> bool:
    return name.lower().endswith(".xml") or data.lstrip()[:5] in (b"<?xml", b"<fact", b"<auto")


BUSY = "Busy reading another picture statement; send this one again in a few minutes."


def _needs_ocr(data: bytes) -> bool:
    """A PDF without a text layer (PacifiCard's screenshots, scans): reading it needs OCR."""
    try:
        return not read_pdf(data).text.strip()
    except PdfError:
        return False  # store_statement refuses it with the reason


@router.post("", response_model=InboxOut, responses={503: {"description": BUSY}})
async def receive(
    file: UploadFile,
    db: DB,
    store: Store,
    sessions: Sessions,
    later: BackgroundTasks,
    sender: Annotated[str, Form(max_length=320)] = "",
) -> InboxOut | JSONResponse:
    """One PDF from a statement email or one invoice XML. Always answers 200 with what happened,
    so the script knows whether to try again. A statement is stored now and read into a batch
    right after the answer: a picture-only statement (PacifiCard) needs text recognition, which
    can take minutes, longer than Azure lets a request wait."""
    data = await file.read(MAX_BYTES + 1)
    user = _who(sender)
    if _is_xml(file.filename or "", data):
        inv = receive_xml(db, data, file.filename or "", user)
        return InboxOut(
            file_name=inv.file_name,
            outcome=inv.outcome,
            message=inv.message,
            status=INVOICE_STATUS[inv.outcome],
            invoice_id=inv.invoice_id,
        )
    if ocr.busy() and _needs_ocr(data):
        # Only one picture is read at a time; the script tries again on its next run.
        return JSONResponse({"detail": BUSY}, status_code=503, headers={"Retry-After": "300"})
    res = store_statement(db, store, data, file.filename or "", user)
    out = InboxOut(
        file_name=res.file_name,
        outcome=res.outcome,
        message=res.message,
        statement_id=res.statement.statement_file_id if res.statement else None,
        status="duplicate" if res.outcome == "duplicate" else "rejected",
    )
    if res.outcome != "stored" or res.statement is None:
        return out

    out.status = "needs_attention"
    sf = db.get(StatementFile, res.statement.statement_file_id)
    if sf is None or not res.statement.can_read or sf.status != "detected":
        out.message = (
            "Stored; open the Import page to choose its account."
            if sf is not None and sf.status == "needs_account"
            else "Stored, but its format isn't recognized; open the Import page."
        )
        return out
    later.add_task(read_statement, sessions, store, sf.statement_file_id, user)
    out.status = "read"
    out.message = "Stored; reading it now. It will wait on the Import page for approval."
    return out


def read_statement(
    sessions: Callable[[], Session], store: StatementStore, statement_id: int, user: str
) -> None:
    """After the answer: read the stored statement into a batch. If it can't be read, it stays
    on the Import page, where Read shows why."""
    with sessions() as db:
        sf = db.get(StatementFile, statement_id)
        if sf is None:
            return
        try:
            stage.parse_statement(db, store, sf, user)
        except stage.StageError as exc:
            db.rollback()
            log.warning("Emailed statement %s not read: %s", statement_id, exc)
        except Exception:  # a background task has nobody to answer: log it, keep the app up
            db.rollback()
            log.exception("Emailed statement %s failed while reading", statement_id)
