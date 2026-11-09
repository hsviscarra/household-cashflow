"""ADR-054: debt payment categories. Synthetic data only."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category
from app.services import classify


def test_debt_categories_make_debt_payments(client: TestClient, db: Session) -> None:
    loans = db.scalar(select(Category).where(Category.name == "Loan Payments"))
    biess = db.scalar(select(Category).where(Category.name == "Mortgage BIESS"))
    assert loans is not None and biess is not None
    assert (loans.kind, biess.kind) == ("debt", "debt")
    assert classify.type_for(loans, Decimal("-3075.36")) == "debt_payment"
    account = db.scalars(select(Account)).first()
    assert account is not None
    assert classify.rule_type("debt", account, Decimal("-500")) == "debt_payment"
    # A new group can be a debt group (e.g. a car loan).
    made = client.post("/api/categories", json={"name": "Car loan", "kind": "debt"})
    assert made.status_code == 201, made.text
    assert made.json()["kind"] == "debt"
