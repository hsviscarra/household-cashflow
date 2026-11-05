"""ADR-024: a statement that ties out is approved as soon as it's read; one that doesn't waits on
the Import page with the reason. Synthetic statements only."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion import stage
from app.models import ImportBatch, RejectedLine, Transaction
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


@pytest.fixture
def auto(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AUTO_APPROVE", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.setenv("AUTO_APPROVE", "false")
    get_settings.cache_clear()


def _upload(client: TestClient, name: str, data: bytes) -> dict:  # type: ignore[type-arg]
    resp = client.post("/api/statements", files=[("files", (name, data, PDF))], headers=USER)
    assert resp.status_code == 200, resp.text
    return resp.json()[0]["statement"]  # type: ignore[no-any-return]


def _batches(db: Session) -> list[ImportBatch]:
    db.expire_all()
    return list(db.scalars(select(ImportBatch).order_by(ImportBatch.batch_id)))


def test_an_upload_that_ties_out_is_read_and_approved(
    auto: None, client: TestClient, db: Session
) -> None:
    _upload(client, "sep.pdf", s.capitalone_full())
    [batch] = _batches(db)
    assert batch.status == "approved"
    assert batch.decided_by == "hernan@example.com (automatic)"
    assert db.scalar(select(func.count()).select_from(Transaction)) > 0
    listed = client.get("/api/statements").json()
    assert listed[0]["batch"]["status"] == "approved"


def test_one_that_does_not_tie_out_waits(auto: None, client: TestClient, db: Session) -> None:
    _upload(client, "bad.pdf", s.capitalone_full(printed_total_delta="5.00"))
    [batch] = _batches(db)
    assert batch.status == "preview" and not batch.tieout_ok
    assert stage.not_ready(db, batch) == "It doesn't tie out."
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_a_break_with_the_previous_statement_waits(
    auto: None, client: TestClient, db: Session
) -> None:
    aug = s.capitalone_full(
        period=("Aug 04, 2026", "Sep 03, 2026"),
        previous="900.00",
        payment="100.00",
        interest="0.00",
        lauren=[("Aug 10", "Aug 11", "UBER EATS SAN JOSE", "200.00")],
        hernan=[],
        payment_dates="Aug 20 Aug 21",
    )
    _upload(client, "aug.pdf", aug)  # closes at 1,000.00
    _upload(client, "sep.pdf", s.capitalone_full(previous="950.00"))  # opens at 950.00
    aug_b, sep_b = _batches(db)
    assert aug_b.status == "approved" and sep_b.status == "preview"


def test_manual_read_approves_too_and_rejects_keep_it_waiting(
    auto: None, client: TestClient, db: Session
) -> None:
    get_settings.cache_clear()
    with pytest.MonkeyPatch.context() as m:
        m.setenv("AUTO_APPROVE", "false")
        get_settings.cache_clear()
        st = _upload(client, "sep.pdf", s.capitalone_full())
    get_settings.cache_clear()
    assert _batches(db) == []  # off: uploads aren't read
    b = client.post(f"/api/statements/{st['statement_file_id']}/read", headers=USER).json()
    assert b["status"] == "approved"

    batch = _batches(db)[0]
    batch.status = "preview"
    db.add(
        RejectedLine(
            statement_file_id=batch.statement_file_id, page=1, line_no=3, text="?", reason="x"
        )
    )
    db.commit()
    assert stage.not_ready(db, batch) == "1 line couldn't be read."
    assert stage.auto_approve(db, batch, "h") is False
    batch.status = "rejected"
    assert stage.not_ready(db, batch) == "Already rejected."


def test_approve_everything_that_checks_out(client: TestClient, db: Session) -> None:
    """The backlog: one click approves every waiting statement that ties out, oldest first."""
    aug = s.capitalone_full(
        period=("Aug 04, 2026", "Sep 03, 2026"),
        previous="900.00",
        payment="100.00",
        interest="0.00",
        lauren=[("Aug 10", "Aug 11", "UBER EATS SAN JOSE", "200.00")],
        hernan=[],
        payment_dates="Aug 20 Aug 21",
    )
    sep = _upload(client, "sep.pdf", s.capitalone_full())
    au = _upload(client, "aug.pdf", aug)
    bad = _upload(client, "bad.pdf", s.produbanco_full(balance_delta="1.00"))
    for st in (sep, au, bad):
        client.post(f"/api/statements/{st['statement_file_id']}/read", headers=USER)
    out = client.post("/api/batches/approve-ready", headers=USER).json()
    assert out["approved"] == 2 and out["loaded"] > 0
    assert [(w["file_name"], w["reason"]) for w in out["waiting"]] == [
        ("bad.pdf", "It doesn't tie out.")
    ]
    statuses = {b.batch_id: b.status for b in _batches(db)}
    assert sorted(statuses.values()) == ["approved", "approved", "preview"]
    assert client.post("/api/batches/approve-ready").json()["approved"] == 0
