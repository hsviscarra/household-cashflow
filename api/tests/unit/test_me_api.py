"""ADR-026: each signed-in person's own settings, and the person filter on transactions."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Transaction

HERNAN = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
LAUREN = {"X-MS-CLIENT-PRINCIPAL-NAME": "lauren@example.com"}


def test_settings_belong_to_each_person(client: TestClient) -> None:
    assert client.get("/api/me/settings", headers=HERNAN).json() == {
        "user": "hernan@example.com",
        "settings": {},
    }
    cols = {"columns": ["date", "amount"], "density": "compact"}
    out = client.put("/api/me/settings/table:transactions", json={"value": cols}, headers=HERNAN)
    assert out.status_code == 200 and out.json()["settings"]["table:transactions"] == cols
    client.put("/api/me/settings/person", json={"value": "Lauren"}, headers=HERNAN)
    client.put("/api/me/settings/person", json={"value": "Hernan"}, headers=HERNAN)  # replaced
    assert client.get("/api/me/settings", headers=HERNAN).json()["settings"] == {
        "table:transactions": cols,
        "person": "Hernan",
    }
    # Lauren sees only hers; without sign-in the app runs as "local".
    assert client.get("/api/me/settings", headers=LAUREN).json()["settings"] == {}
    assert client.get("/api/me/settings").json()["user"] == "local"

    assert client.delete("/api/me/settings/person", headers=HERNAN).status_code == 204
    assert client.delete("/api/me/settings/person", headers=HERNAN).status_code == 204
    left = client.get("/api/me/settings", headers=HERNAN).json()["settings"]
    assert list(left) == ["table:transactions"]


def test_bad_keys_and_large_values_are_refused(client: TestClient) -> None:
    assert client.put("/api/me/settings/Bad Key", json={"value": 1}).status_code == 422
    big = {"value": "x" * 20_001}
    assert client.put("/api/me/settings/views", json=big).status_code == 413
    for i in range(100):
        assert client.put(f"/api/me/settings/k{i}", json={"value": i}).status_code == 200
    assert client.put("/api/me/settings/one-more", json={"value": 1}).status_code == 409
    assert client.put("/api/me/settings/k5", json={"value": 6}).status_code == 200  # update ok


def test_transactions_by_person(client: TestClient, db: Session) -> None:
    account = db.scalar(select(Account).where(Account.kind == "checking"))
    assert account is not None
    for i, person in enumerate(("Hernan", "Lauren", "Joint", None)):
        db.add(
            Transaction(
                natural_key=f"p-{i}",
                account_id=account.account_id,
                txn_date=date(2026, 10, 1 + i),
                cash_month=date(2026, 10, 1),
                amount=Decimal("-10"),
                description_raw=f"LINE {i}",
                type="expense",
                person=person,
                source="manual",
                status="confirmed",
            )
        )
    db.commit()

    def who(person: str | None = None) -> list[str]:
        params = {"person": person} if person else {}
        return [t["description"] for t in client.get("/api/transactions", params=params).json()]

    assert len(who()) == 4
    assert who("Hernan") == ["LINE 0"] and who("Lauren") == ["LINE 1"]
    assert who("Joint") == ["LINE 3", "LINE 2"]  # no person counts as joint
    assert client.get("/api/transactions", params={"person": "x"}).status_code == 422


def test_transactions_by_person_and_over_months(client: TestClient, db: Session) -> None:
    """ADR-030: lines for one person from People, over several months."""
    from app.models import Counterparty

    account = db.scalar(select(Account).where(Account.kind == "checking"))
    assert account is not None
    ruben = Counterparty(name="Rubén")
    db.add(ruben)
    db.flush()
    for i, month in enumerate((7, 8, 9, 10)):
        db.add(
            Transaction(
                natural_key=f"m-{i}",
                account_id=account.account_id,
                txn_date=date(2026, month, 3),
                cash_month=date(2026, month, 1),
                amount=Decimal("-100"),
                description_raw=f"TRANSFERENCIA {i}",
                type="transfer",
                counterparty_id=ruben.counterparty_id if month != 8 else None,
                source="statement",
                status="confirmed",
            )
        )
    db.commit()

    def got(**params: object) -> list[str]:
        return [t["description"] for t in client.get("/api/transactions", params=params).json()]

    assert got(month="2026-10-01") == ["TRANSFERENCIA 3"]
    assert got(month="2026-10-01", months=3) == [
        "TRANSFERENCIA 3",
        "TRANSFERENCIA 2",
        "TRANSFERENCIA 1",
    ]
    who = ruben.counterparty_id
    assert got(month="2026-10-01", months=12, counterparty_id=who) == [
        "TRANSFERENCIA 3",
        "TRANSFERENCIA 2",
        "TRANSFERENCIA 0",
    ]
    assert client.get("/api/transactions", params={"months": 40}).status_code == 422
