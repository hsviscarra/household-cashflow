"""ADR-044: bank sync through SimpleFIN. Synthetic data only; SimpleFIN is faked."""

import base64
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Account, Category, LoadLog, Transaction
from app.services import bank_sync
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
ACCESS = "https://user%40x:p%3Ass@bridge.example/simplefin"


def _epoch(y: int, m: int, d: int) -> int:
    return int(datetime(y, m, d, 12, tzinfo=UTC).timestamp())


def _feed() -> dict[str, Any]:
    return {
        "errors": ["Capital One needs you to sign in again."],
        "accounts": [
            {
                "id": "ACT-BOFA",
                "org": {"name": "Bank of America"},
                "name": "Adv Plus Banking",
                "balance": "2000.00",
                "balance-date": _epoch(2026, 9, 16),
                "transactions": [
                    {
                        "id": "T1",
                        "posted": _epoch(2026, 9, 11),
                        "amount": "-200.00",
                        "description": "Zelle payment to TEST PERSON",
                    },
                    {
                        "id": "T2",
                        "posted": _epoch(2026, 9, 8),
                        "amount": "-30.00",
                        "description": "PAYPAL *FABLETICS",
                    },
                    {
                        "id": "T3",
                        "posted": _epoch(2026, 9, 15),
                        "amount": "-12.00",
                        "description": "COFFEE",
                        "pending": True,
                    },
                    {
                        "id": "T4",
                        "posted": _epoch(2026, 9, 15),
                        "amount": "-9.99",
                        "description": "AUTHORIZATION THAT NEVER POSTED",
                    },
                    {"id": "T5", "posted": "bad", "amount": "-1.00", "description": "X"},
                ],
            },
            {
                "id": "ACT-CAP1",
                "org": {"name": "Capital One"},
                "name": "Quicksilver",
                "balance": "-120.50",
                "transactions": [
                    {
                        "id": "C1",
                        "posted": _epoch(2026, 9, 10),
                        "amount": "-20.00",
                        "description": "UBER",
                    },
                ],
            },
        ],
    }


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, dict[str, str]]]]:
    calls: list[tuple[str, dict[str, str]]] = []

    def fake(url: str, headers: dict[str, str]) -> dict[str, Any]:
        calls.append((url, headers))
        return _feed()

    monkeypatch.setenv("SIMPLEFIN_ACCESS_URL", ACCESS)
    get_settings.cache_clear()
    monkeypatch.setattr(bank_sync, "_http_get", fake)
    yield calls
    monkeypatch.delenv("SIMPLEFIN_ACCESS_URL")
    get_settings.cache_clear()


def _age_last_run(db: Session) -> None:
    db.execute(update(LoadLog).values(loaded_at=datetime(2026, 1, 1)))
    db.commit()


def _synced(db: Session) -> list[Transaction]:
    db.expire_all()
    q = select(Transaction).where(Transaction.source == "bank_sync").order_by(Transaction.txn_date)
    return list(db.scalars(q))


def test_request_keeps_credentials_out_of_the_url() -> None:
    from datetime import date

    url, headers = bank_sync._request("https://a:b@h.example:8443/sf/", date(2026, 9, 1))
    assert url.startswith("https://h.example:8443/sf/accounts?start-date=")
    assert "a:b" not in url
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"a:b").decode()
    with pytest.raises(bank_sync.SyncError):
        bank_sync._request("http://a:b@h.example/sf", date(2026, 9, 1))
    assert bank_sync._money("x") is None and bank_sync._day(None) is None


def test_not_set_up(client: TestClient) -> None:
    assert client.get("/api/bank-sync").json()["configured"] is False
    assert client.post("/api/bank-sync/run").status_code == 409
    assert client.post("/api/bank-sync/run", params={"auto": True}).json()["ran"] is False


def test_sync_then_statement_takes_over(
    client: TestClient, db: Session, feed: list[tuple[str, dict[str, str]]]
) -> None:
    today = {"today": "2026-09-16"}
    first = client.post("/api/bank-sync/run", params={"auto": True, **today}, headers=USER).json()
    assert first["ran"] is True and first["added"] == 0  # nothing linked yet
    url, headers = feed[0]
    assert "user" not in url and headers["Authorization"].startswith("Basic ")
    assert base64.b64decode(headers["Authorization"][6:]) == b"user@x:p:ss"
    run = first["last_run"]
    assert run["unlinked"] == 5 and run["errors"] == ["Capital One needs you to sign in again."]
    assert [a["org"] for a in run["accounts"]] == ["Bank of America", "Capital One"]
    # Run automatically again right away: skipped. By hand: too soon.
    again = client.post("/api/bank-sync/run", params={"auto": True}).json()
    assert again["ran"] is False
    assert client.post("/api/bank-sync/run").status_code == 429

    checking = db.scalars(select(Account).where(Account.last4 == "8872")).one()
    linked = client.put(
        "/api/bank-sync/link", json={"sync_id": "ACT-BOFA", "account_id": checking.account_id}
    ).json()
    assert {a["sync_id"] for a in linked["accounts"]} >= {"ACT-BOFA"}
    _age_last_run(db)
    out = client.post("/api/bank-sync/run", params=today, headers=USER).json()
    assert out["added"] == 3 and out["pending_lines"] == 3  # the pending one waits
    rows = _synced(db)
    assert [(str(r.amount), r.status) for r in rows] == [
        ("-30.0000", "pending"),
        ("-200.0000", "pending"),
        ("-9.9900", "pending"),
    ]
    assert rows[0].category_id is not None  # the PayPal rule categorized it
    assert rows[0].person == checking.owner

    # Hernan categorizes the Zelle by hand while it waits for the statement.
    gifts = db.scalars(select(Category).where(Category.parent_id.is_not(None))).first()
    assert gifts is not None
    zelle = rows[1]
    zelle.category_id, zelle.category_source, zelle.notes = gifts.category_id, "manual", "Birthday"
    db.commit()

    # Synced again: nothing new.
    _age_last_run(db)
    out = client.post("/api/bank-sync/run", params=today).json()
    assert out["added"] == 0 and out["last_run"]["already"] == 3

    # The statement arrives: it takes their place and keeps the hand work.
    st = client.post(
        "/api/statements", files=[("files", ("bofa.pdf", s.bofa_full(), PDF))], headers=USER
    ).json()[0]["statement"]
    batch = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    if batch.get("status") == "preview":
        assert client.post(f"/api/batches/{batch['batch_id']}/approve", headers=USER).is_success
    assert _synced(db) == []
    stmt_zelle = db.scalars(
        select(Transaction).where(
            Transaction.source == "statement", Transaction.description_raw.like("Zelle%")
        )
    ).one()
    assert (stmt_zelle.category_id, stmt_zelle.category_source, stmt_zelle.notes) == (
        gifts.category_id,
        "manual",
        "Birthday",
    )

    # Later syncs leave alone what the statement covers.
    _age_last_run(db)
    out = client.post("/api/bank-sync/run", params=today).json()
    assert out["added"] == 0 and out["last_run"]["covered"] == 3

    # Unlink.
    out = client.put("/api/bank-sync/link", json={"sync_id": "ACT-BOFA", "account_id": None}).json()
    assert all(a["sync_id"] is None for a in out["accounts"])
    assert (
        client.put("/api/bank-sync/link", json={"sync_id": "X", "account_id": 9999}).status_code
        == 404
    )


def test_sync_error_is_reported(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, feed: list[Any]
) -> None:
    def broken(url: str, headers: dict[str, str]) -> dict[str, Any]:
        raise OSError("connection refused to " + url)

    monkeypatch.setattr(bank_sync, "_http_get", broken)
    r = client.post("/api/bank-sync/run")
    assert r.status_code == 502 and "bridge.example" not in r.text


def test_not_due_without_setup(db: Session) -> None:
    assert bank_sync.due(db) is False
