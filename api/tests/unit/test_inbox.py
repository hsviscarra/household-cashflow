"""F20: statements by email. The Gmail script's endpoint: its token, a statement read into a batch
waiting for approval, the same email again, files that need a person, and files refused.
Synthetic statements only."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
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
    assert out["message"] == "Stored; reading it now. It will wait on the Import page for approval."
    # Read right after the answer (TestClient runs the background task before returning).
    batch = db.scalars(
        select(ImportBatch).where(ImportBatch.statement_file_id == out["statement_id"])
    ).one()
    assert batch.status == "preview" and batch.tieout_ok
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
    inbox: None,
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reading fails after the answer: the statement stays on the Import page (Read shows why),
    and the app keeps going, whatever the error."""
    errors: list[Exception] = [
        stage.StageError("The statement could not be read: no lines.", 422),
        RuntimeError("OCR crashed"),
    ]

    def broken(*args: object) -> ImportBatch:
        raise errors.pop(0)

    monkeypatch.setattr(stage, "parse_statement", broken)
    out = post(client, s.capitalone_full())
    assert (out["outcome"], out["status"]) == ("stored", "read")
    assert "not read: The statement could not be read: no lines." in caplog.text
    out2 = post(client, s.capitalone_full(previous="900.00"))
    assert out2["status"] == "read" and "failed while reading" in caplog.text
    assert db.scalar(select(func.count()).select_from(ImportBatch)) == 0
    listed = {st["statement_file_id"]: st for st in client.get("/api/statements").json()}
    assert listed[out["statement_id"]]["can_read"] and listed[out["statement_id"]]["batch"] is None


def test_read_statement_gone(engine: Engine, store: object) -> None:
    from sqlalchemy.orm import sessionmaker

    from app.routers import inbox as inbox_router

    # Deleted before the task ran: nothing to do.
    inbox_router.read_statement(sessionmaker(bind=engine), store, 999, "gmail")  # type: ignore[arg-type]


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


# ---------------------------------------------------------------- one picture at a time
def test_busy_while_reading_a_picture(inbox: None, client: TestClient) -> None:
    """While one picture statement is read, another picture-only PDF is asked to come back later
    (503, the script retries next run); a PDF with a text layer still goes through."""
    from app.ingestion import ocr

    picture = s.scanned(s.capitalone_full())
    assert ocr._READING.acquire(blocking=False)
    try:
        assert ocr.busy()
        resp = client.post(
            "/api/inbox", files={"file": ("p.pdf", picture, "application/pdf")}, headers=AUTH
        )
        assert resp.status_code == 503 and resp.headers["retry-after"] == "300"
        assert "send this one again" in resp.json()["detail"]
        assert post(client, s.diners_full())["outcome"] == "stored"  # text layer: not blocked
        assert post(client, b"not a pdf")["status"] == "rejected"  # refused as before
    finally:
        ocr._READING.release()
    assert not ocr.busy()


def test_tesseract_timeouts_are_errors_not_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from PIL import Image

    from app.ingestion import ocr

    def slow(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired("tesseract", 120)

    def failed(*args: object, **kwargs: object) -> object:
        raise subprocess.CalledProcessError(1, "tesseract")

    image = Image.new("L", (10, 10), 255)
    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(ocr.OcrError, match="took too long"):
        ocr._tesseract(image)
    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(ocr.OcrError, match="exit code 1"):
        ocr._tesseract(image)
