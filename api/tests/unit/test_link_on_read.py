"""A statement covering two accounts (BofA checking and savings) but linked to only one when it
was uploaded: reading it links the other by its last four digits instead of failing (uploading
the same file again is refused as a duplicate)."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, StatementFile
from tests.fixtures.statements import bofa_full

PDF = "application/pdf"


def _upload_linked_to_checking_only(client: TestClient, db: Session) -> int:
    st = client.post("/api/statements", files=[("files", ("eStmt (1).pdf", bofa_full(), PDF))])
    sid: int = st.json()[0]["statement"]["statement_file_id"]
    sf = db.get(StatementFile, sid)
    assert sf is not None
    sf.accounts = [a for a in sf.accounts if a.last4 == "8872"]
    db.commit()
    return sid


def test_reading_links_the_missing_account(client: TestClient, db: Session) -> None:
    sid = _upload_linked_to_checking_only(client, db)
    batch = client.post(f"/api/statements/{sid}/read").json()
    assert batch["tieout_ok"], batch.get("detail", batch.get("checks"))
    listed = next(s for s in client.get("/api/statements").json() if s["statement_file_id"] == sid)
    assert sorted(a["last4"] for a in listed["accounts"]) == ["1862", "8872"]


def test_no_account_with_those_digits_says_what_to_do(client: TestClient, db: Session) -> None:
    sid = _upload_linked_to_checking_only(client, db)
    savings = db.scalar(select(Account).where(Account.last4 == "1862"))
    assert savings is not None
    savings.last4 = None
    db.commit()
    resp = client.post(f"/api/statements/{sid}/read")
    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "The statement covers account •••• 1862, which no active account has as its last four "
        "digits. Set them in Settings → Accounts, then read the statement again."
    )
