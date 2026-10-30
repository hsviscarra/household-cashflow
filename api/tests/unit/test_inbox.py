"""F20: statements by email. The Gmail script's endpoint: its token, a statement read into a batch
waiting for approval, the same email again, files that need a person, and files refused.
Synthetic statements only."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion import stage
from app.models import ImportBatch, StatementFile, Transaction
from tests.fixtures import statements as s

TOKEN = "i" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SENDER = "estadodecuenta@bank.example"


@pytest.fixture
def inbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("INBOX_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("INBOX_TOKEN")
    get_settings.cache_clear()


def post(client: TestClient, data: bytes, name: str = "statement.pdf", **headers: str) -> dict:  # type: ignore[type-arg]
    resp = client.post(
        "/api/inbox",
        files={"file": (name, data, "application/octet-stream")},
        data={"sender": SENDER},
        headers=headers or AUTH,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


def test_off_without_a_token(client: TestClient) -> None:
    resp = client.post("/api/inbox", files={"file": ("a.pdf", b"x", "application/pdf")})
    assert resp.status_code == 404 and resp.json()["detail"] == "The inbox is off."


def test_needs_the_token_not_a_sign_in(
    inbox: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The household's allow-list doesn't apply: the script has no signed-in person, only the token.
    monkeypatch.setenv("ALLOWED_EMAILS", "hernan@example.com")
    get_settings.cache_clear()
    files = {"file": ("a.pdf", s.capitalone_full(), "application/pdf")}
    assert client.post("/api/inbox", files=files).status_code == 401
    wrong = client.post("/api/inbox", files=files, headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    assert client.post("/api/inbox", files=files, headers=AUTH).status_code == 200
    # The token opens only the inbox, not the people's pages.
    assert client.get("/api/statements", headers=AUTH).status_code == 403
    monkeypatch.delenv("ALLOWED_EMAILS")
    get_settings.cache_clear()


def test_a_statement_is_read_and_waits_for_approval(
    inbox: None, client: TestClient, db: Session
) -> None:
    out = post(client, s.capitalone_full(), "Statement_102026_4003.pdf")
    assert (out["outcome"], out["status"]) == ("stored", "read")
    assert out["message"] == "Read; waiting for approval on the Import page."
    batch = db.get(ImportBatch, out["batch_id"])
    assert batch is not None and batch.status == "preview" and batch.tieout_ok
    assert batch.created_by == f"gmail ({SENDER})"
    sf = db.get(StatementFile, out["statement_id"])
    assert sf is not None and sf.uploaded_by == f"gmail ({SENDER})"
    # Nothing is loaded until a person approves it.
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    listed = client.get("/api/statements").json()
    assert listed[0]["batch"]["status"] == "preview"

    # The same email again (the script retrying) is a harmless duplicate.
    again = post(client, s.capitalone_full(), "copy.pdf")
    assert (again["outcome"], again["status"], again["batch_id"]) == (
        "duplicate",
        "duplicate",
        None,
    )
    assert again["statement_id"] == out["statement_id"]
    assert db.scalar(select(func.count()).select_from(ImportBatch)) == 1


def test_files_that_need_a_person(inbox: None, client: TestClient) -> None:
    unknown = post(client, s.unknown())
    assert (unknown["outcome"], unknown["status"]) == ("stored", "needs_attention")
    assert "format isn't recognized" in unknown["message"] and unknown["batch_id"] is None

    other_card = post(client, s.diners("TITULAR DE PRUEBA", "9999"))  # no name to go by
    assert other_card["status"] == "needs_attention"
    assert other_card["message"] == "Stored; open the Import page to choose its account."


def test_stored_but_not_read(
    inbox: None, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> ImportBatch:
        raise stage.StageError("The statement could not be read: no lines.", 422)

    monkeypatch.setattr(stage, "parse_statement", broken)
    out = post(client, s.capitalone_full())
    assert (out["outcome"], out["status"]) == ("stored", "needs_attention")
    assert out["message"] == "Stored, but not read: The statement could not be read: no lines."


def test_refused_files(inbox: None, client: TestClient) -> None:
    locked = post(client, s.encrypted())
    assert (locked["outcome"], locked["status"], locked["statement_id"]) == (
        "rejected",
        "rejected",
        None,
    )
    empty = post(client, b"")
    assert empty["status"] == "rejected" and empty["message"] == "The file is empty."
    resp = client.post("/api/inbox", data={"sender": SENDER}, headers=AUTH)
    assert resp.status_code == 422  # no file at all
