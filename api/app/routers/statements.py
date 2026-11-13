"""Statement upload and list (F3)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.config import get_settings
from app.db.session import get_session, get_session_factory
from app.ingestion import stage
from app.ingestion.preview import latest_batches
from app.ingestion.storage import StatementStore, get_store
from app.ingestion.upload import MAX_BYTES, store_statement, to_out
from app.models import Account, StatementFile
from app.schemas import StatementOut, StatementPatch, UploadResultOut

router = APIRouter(prefix="/api/statements", tags=["statements"])
DB = Annotated[Session, Depends(get_session)]
Store = Annotated[StatementStore, Depends(get_store)]
Sessions = Annotated[Callable[[], Session], Depends(get_session_factory)]
MAX_FILES = 50


@router.post("", response_model=list[UploadResultOut])
async def upload(
    files: list[UploadFile],
    request: Request,
    db: DB,
    store: Store,
    sessions: Sessions,
    later: BackgroundTasks,
) -> list[UploadResultOut]:
    """Store uploaded statement PDFs; a file already stored is reported as a duplicate, not stored
    twice."""
    if len(files) > MAX_FILES:
        raise HTTPException(422, f"Upload at most {MAX_FILES} files at a time.")
    out = []
    for f in files:
        data = await f.read(MAX_BYTES + 1)
        res = store_statement(db, store, data, f.filename or "", current_user(request))
        out.append(res)
        st = res.statement
        if (
            get_settings().auto_approve
            and res.outcome == "stored"
            and st is not None
            and st.can_read
            and st.status == "detected"
        ):
            # Read after the answer, and approve if it ties out (ADR-024).
            later.add_task(
                stage.read_and_approve, sessions, store, st.statement_file_id, current_user(request)
            )
    return out


@router.get("", response_model=list[StatementOut])
def list_statements(db: DB) -> list[StatementOut]:
    """Every stored statement, newest first, with its latest batch."""
    batches = latest_batches(db)
    rows = db.scalars(
        select(StatementFile).order_by(
            StatementFile.uploaded_at.desc(), StatementFile.statement_file_id.desc()
        )
    ).all()  # in full before to_out loads each one's accounts (one open result per connection)
    return [to_out(sf, batches.get(sf.statement_file_id)) for sf in rows]


def _get(db: Session, statement_id: int) -> StatementFile:
    sf = db.get(StatementFile, statement_id)
    if sf is None:
        raise HTTPException(404, f"Statement {statement_id} not found.")
    return sf


@router.patch("/{statement_id}", response_model=StatementOut)
def assign_accounts(statement_id: int, body: StatementPatch, db: DB) -> StatementOut:
    """Say which accounts a statement belongs to."""
    sf = _get(db, statement_id)
    accounts = list(db.scalars(select(Account).where(Account.account_id.in_(body.account_ids))))
    if len(accounts) != len(set(body.account_ids)):
        raise HTTPException(404, "One of the accounts does not exist.")
    sf.accounts = accounts
    sf.account_match = "manual"
    if sf.status == "needs_account":
        sf.status = "detected"
    db.commit()
    db.refresh(sf)
    return to_out(sf)


@router.get("/{statement_id}/file")
def download(statement_id: int, db: DB, store: Store) -> Response:
    """The statement's PDF as it was uploaded."""
    sf = _get(db, statement_id)
    safe = sf.file_name.replace('"', "")
    return Response(
        store.get(sf.blob_key),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe}"'},
    )
