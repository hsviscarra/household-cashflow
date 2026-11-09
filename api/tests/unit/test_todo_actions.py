"""ADR-058: To do acts and lets go. Synthetic data only."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Transaction
from app.services import sources, todo
from tests.unit.test_costs_api import _line


def _section(client: TestClient, key: str) -> dict | None:  # type: ignore[type-arg]
    body = client.get("/api/todo", params={"today": "2026-09-20"}).json()
    return next((s for s in body["sections"] if s["key"] == key), None)


def test_generic_descriptions_get_no_rule() -> None:
    assert not todo.rule_ok("TRANSFERENCIA INTERNET")
    assert not todo.rule_ok('SU PAGO "MUCHAS GRACIAS"'.replace('"', ""))
    assert not todo.rule_ok("")
    assert todo.rule_ok("CAPITAL ONE MOBILE PYMT")
    assert todo.rule_ok("ZELLE PAYMENT TO NAPOLES TRANSPORT")


def test_transfers_only_in_statement_months_and_one_sided(client: TestClient, db: Session) -> None:
    card = db.scalar(select(Account).where(Account.kind == "credit_card"))
    assert card is not None
    _line(
        db, card.account_id, date(2026, 1, 5), "282.00", "SU PAGO MUCHAS GRACIAS", None, "transfer"
    )
    _line(
        db, card.account_id, date(2026, 8, 5), "40.24", "SU PAGO MUCHAS GRACIAS", None, "transfer"
    )
    for t in db.scalars(select(Transaction).where(Transaction.description_raw.like("SU PAGO%"))):
        t.source = "statement"
    db.commit()
    sources.set_statements_from(db, date(2026, 7, 1), "test")
    sec = _section(client, "transfers")
    assert sec is not None and sec["count"] == 1  # January is a workbook month
    task = sec["tasks"][0]
    assert Decimal(task["amount"]) == Decimal("40.24") and task["data"]["rule_ok"] is False
    assert task["data"]["account_kind"] == "credit_card"

    tid = task["data"]["transaction_id"]
    assert client.post(f"/api/transfers/{tid}/one-sided").status_code == 204
    assert _section(client, "transfers") is None
    line = db.get(Transaction, tid)
    db.refresh(line)
    assert line is not None and line.transfer_group_id == tid
    assert client.post(f"/api/transfers/{tid}/one-sided").status_code == 409
    assert client.post("/api/transfers/999999/one-sided").status_code == 404
    # Unlinking asks again.
    assert client.delete(f"/api/transfers/{tid}").status_code == 204
    assert _section(client, "transfers") is not None


def test_a_value_let_go_is_not_asked_again(client: TestClient) -> None:
    old = {"name": "Fondo", "holding_class": "cash", "value": "500", "as_of": "2026-05-31"}
    assert client.post("/api/holdings", json=old).status_code == 201
    sec = _section(client, "values")
    assert sec is not None
    task = next(t for t in sec["tasks"] if t["title"] == "Fondo")
    assert task["data"]["source"] == "manual"
    for _ in range(2):  # twice is fine
        assert client.post("/api/todo/dismiss", json={"key": task["key"]}).status_code == 204
    sec = _section(client, "values")
    assert sec is None or all(t["title"] != "Fondo" for t in sec["tasks"])
