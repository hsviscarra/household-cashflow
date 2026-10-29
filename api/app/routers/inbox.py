"""Statements by email (F20, ADR-020): the Gmail script posts each statement PDF here.

The script runs in Hernan's Gmail every hour, finds the banks' statement emails and posts their
PDF attachments with the inbox bearer token (checked in app.auth). Each file is stored exactly
like an upload (a file already uploaded is a duplicate, so posting it again is harmless), then,
when its bank and account are recognized, read into a batch that waits on the Import page for
approval. Nothing reaches the household's transactions without that approval.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.ingestion import stage
from app.ingestion.storage import StatementStore, get_store
from app.ingestion.upload import MAX_BYTES, store_statement
from app.models import StatementFile

router = APIRouter(prefix="/api/inbox", tags=["inbox"])
DB = Annotated[Session, Depends(get_session)]
Store = Annotated[StatementStore, Depends(get_store)]


class InboxOut(BaseModel):
    file_name: str
    outcome: Literal["stored", "duplicate", "rejected"]
    message: str
    statement_id: int | None = None
    # "read": a batch waits on the Import page; "needs_attention": stored, but it needs a person
    # (an unknown format, an account to choose, or a statement that couldn't be read).
    status: Literal["read", "needs_attention", "duplicate", "rejected"]
    batch_id: int | None = None


def _who(sender: str) -> str:
    sender = sender.strip()
    return f"gmail ({sender})"[:320] if sender else "gmail"


@router.post("", response_model=InboxOut)
async def receive(
    file: UploadFile,
    db: DB,
    store: Store,
    sender: Annotated[str, Form(max_length=320)] = "",
) -> InboxOut:
    """One PDF from a statement email: stored, then read into a batch for approval when it can
    be. Always answers 200 with what happened, so the script knows whether to try again."""
    data = await file.read(MAX_BYTES + 1)
    user = _who(sender)
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
    try:
        batch = stage.parse_statement(db, store, sf, user)
    except stage.StageError as exc:
        db.rollback()
        out.message = f"Stored, but not read: {exc}"
        return out
    out.status, out.batch_id = "read", batch.batch_id
    out.message = "Read; waiting for approval on the Import page."
    return out
