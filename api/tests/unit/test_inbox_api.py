"""ADR-029: autopilot for Claude's sure suggestions (with undo), many merchants at once, and
"who?" for transfers that don't say who."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MerchantRule, Transaction
from app.services import inbox, suggest
from tests.unit.test_classify_api import _cat, loaded, with_key  # noqa: F401

TRANSFER = "TRANSFERENCIA CTAS TERCEROS BCA ENL"
VISA = "DEBITO VISA"


def _fake(monkeypatch: pytest.MonkeyPatch, answers: list[suggest.Answer]) -> None:
    def fake(asked: list[suggest.Asked], *_a: object) -> list[suggest.Answer]:
        keys = {x.merchant_key for x in asked}
        return [a for a in answers if a.merchant_key in keys]

    monkeypatch.setattr(suggest, "call_claude", fake)


def _keys(client: TestClient) -> set[str]:
    return {g["merchant_key"] for g in client.get("/api/review").json()["groups"]}


def test_autopilot_accepts_sure_suggestions_and_undo_puts_them_back(
    loaded: TestClient,  # noqa: F811
    db: Session,
    with_key: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake(
        monkeypatch,
        [
            suggest.Answer(TRANSFER, "Office Rent", Decimal("0.95"), "rent"),
            suggest.Answer(VISA, "groceries/Supermarket", Decimal("0.62"), "card"),
        ],
    )
    done = inbox.autopilot(db, "hernan@example.com")
    assert (done.asked, done.suggested, done.merchants) == (3, 2, 1)
    assert done.lines >= 1
    keys = _keys(loaded)
    assert TRANSFER not in keys and VISA in keys  # 62% waits for a person

    auto = loaded.get("/api/review/auto").json()
    assert auto["on"] is True and Decimal(auto["threshold"]) == Decimal("0.90")
    [rule] = auto["rules"]
    assert rule["pattern"] == TRANSFER and rule["category_path"] == "Office Rent"
    assert rule["lines"] == done.lines and rule["is_active"] is True
    line = db.scalar(select(Transaction).where(Transaction.description_raw.like(f"{TRANSFER}%")))
    assert line is not None and line.category_source == "suggestion"
    before_type = "income"

    undone = loaded.post(f"/api/review/auto/{rule['rule_id']}/undo").json()
    assert undone["lines"] == rule["lines"]
    assert TRANSFER in _keys(loaded)
    db.expire_all()
    assert db.get(MerchantRule, rule["rule_id"]).is_active is False  # type: ignore[union-attr]
    line = db.get(Transaction, line.transaction_id)
    assert line is not None and line.category_id is None and line.type == before_type
    assert loaded.get("/api/review/auto").json()["rules"] == []
    assert loaded.post("/api/review/auto/999999/undo").status_code == 404


def test_autopilot_is_quiet_when_off_or_failing(
    loaded: TestClient,  # noqa: F811
    db: Session,
    with_key: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_a: object) -> list[suggest.Answer]:
        raise suggest.SuggestError("Claude is down", 502)

    monkeypatch.setattr(suggest, "call_claude", broken)
    assert inbox.autopilot(db, "x") == inbox.Autopilot()
    monkeypatch.setenv("AUTO_ACCEPT_CONFIDENCE", "0")
    get_settings.cache_clear()
    assert inbox.autopilot(db, "x") == inbox.Autopilot()
    assert loaded.get("/api/review/auto").json()["on"] is False


def test_autopilot_needs_a_key(db: Session) -> None:
    assert inbox.autopilot(db, "x") == inbox.Autopilot()


def test_many_merchants_at_once(loaded: TestClient, db: Session) -> None:  # noqa: F811
    rent = _cat(db, "Office Rent")
    keys = sorted(_keys(loaded))
    out = loaded.post(
        "/api/review/resolve-many",
        json={"merchant_keys": [VISA, TRANSFER, "NOT THERE"], "category_id": rent},
    ).json()
    assert (out["merchants"], out["skipped"]) == (2, 1)
    assert out["lines"] >= 2
    assert _keys(loaded) == set(keys) - {VISA, TRANSFER}
    assert db.scalar(select(MerchantRule).where(MerchantRule.pattern == VISA)) is not None
    # Each to its suggestion: none here, so every one is skipped.
    left = sorted(_keys(loaded))
    out = loaded.post("/api/review/resolve-many", json={"merchant_keys": left}).json()
    assert (out["merchants"], out["skipped"]) == (0, len(left))
    bad = {"merchant_keys": left, "category_id": 999999}
    assert loaded.post("/api/review/resolve-many", json=bad).status_code == 404
    assert loaded.post("/api/review/resolve-many", json={"merchant_keys": []}).status_code == 422


def test_who_gets_a_person(loaded: TestClient, db: Session) -> None:  # noqa: F811
    lines = loaded.get("/api/review/who", params={"month": "2026-08-01"}).json()
    line = next(t for t in lines if t["description"].startswith(TRANSFER))
    assert all("VISA" not in t["description"] for t in lines)
    assert loaded.get("/api/review/who").status_code == 200

    held = _cat(db, "Savings & Debt")
    person = loaded.post("/api/people", json={"name": "Rubén", "category_id": held}).json()
    out = loaded.post(
        "/api/review/who",
        json={
            "transaction_id": line["transaction_id"],
            "counterparty_id": person["counterparty_id"],
        },
    )
    assert out.status_code == 200
    row = db.get(Transaction, line["transaction_id"])
    db.refresh(row)
    assert row is not None and row.counterparty_id == person["counterparty_id"]
    again = loaded.get("/api/review/who", params={"month": "2026-08-01"}).json()
    assert line["transaction_id"] not in {t["transaction_id"] for t in again}

    missing = {"transaction_id": 999999, "counterparty_id": person["counterparty_id"]}
    assert loaded.post("/api/review/who", json=missing).status_code == 404
    nobody = {"transaction_id": line["transaction_id"], "counterparty_id": 999999}
    assert loaded.post("/api/review/who", json=nobody).status_code == 404


def test_approve_ready_reports_autopilot(client: TestClient) -> None:
    out = client.post("/api/batches/approve-ready").json()
    assert (out["auto_merchants"], out["auto_lines"]) == (0, 0)
