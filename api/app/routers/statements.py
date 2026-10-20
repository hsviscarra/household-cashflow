"""Statement upload and list (F3)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PRINCIPAL_HEADER
from app.db.session import get_session
from app.ingestion.storage import StatementStore, get_store
from app.ingestion.upload import MAX_BYTES, store_statement, to_out
from app.models import Account, StatementFile
from app.schemas import StatementOut, StatementPatch, UploadResultOut

router = APIRouter(prefix="/api/statements", tags=["statements"])
DB = Annotated[Session, Depends(get_session)]
Store = Annotated[StatementStore, Depends(get_store)]
MAX_FILES = 50


def _user(request: Request) -> str:
    return (request.headers.get(PRINCIPAL_HEADER) or "local").strip().lower()


@router.post("", response_model=list[UploadResultOut])
async def upload(
    files: list[UploadFile], request: Request, db: DB, store: Store
) -> list[UploadResultOut]:
    if len(files) > MAX_FILES:
        raise HTTPException(422, f"Upload at most {MAX_FILES} files at a time.")
    out = []
    for f in files:
        data = await f.read(MAX_BYTES + 1)
        out.append(store_statement(db, store, data, f.filename or "", _user(request)))
    return out


@router.get("", response_model=list[StatementOut])
def list_statements(db: DB) -> list[StatementOut]:
    rows = db.scalars(
        select(StatementFile).order_by(
            StatementFile.uploaded_at.desc(), StatementFile.statement_file_id.desc()
        )
    )
    return [to_out(sf) for sf in rows]


def _get(db: Session, statement_id: int) -> StatementFile:
    sf = db.get(StatementFile, statement_id)
    if sf is None:
        raise HTTPException(404, f"Statement {statement_id} not found.")
    return sf


@router.patch("/{statement_id}", response_model=StatementOut)
def assign_accounts(statement_id: int, body: StatementPatch, db: DB) -> StatementOut:
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
    sf = _get(db, statement_id)
    safe = sf.file_name.replace('"', "")
    return Response(
        store.get(sf.blob_key),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe}"'},
    )
