"""ADR-056: the new house's down payment, paid off as a debt. Synthetic data only."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, ChangeLog, MerchantRule, Transaction
from app.seeds import NEW_HOUSE, NEW_HOUSE_RULE
from app.services import classify
from app.services import rules as rule_engine
from tests.unit.test_costs_api import _line


def _new_house(db: Session) -> Category:
    c = db.scalar(select(Category).where(Category.name == NEW_HOUSE[1]))
    assert c is not None and c.kind == "debt"
    return c


def test_trust_payments_are_new_house_debt_payments(db: Session) -> None:
    house = _new_house(db)
    rule = db.scalar(select(MerchantRule).where(MerchantRule.pattern == NEW_HOUSE_RULE))
    assert rule is not None and rule.category_id == house.category_id
    line = "TRANSFERENCIA FIDEICOMISO INMOBILIARIO KALANI CUOTA 3"
    assert rule_engine.matches(rule_engine.Rule.of(rule), line, Decimal("-3075.36"))
    assert classify.type_for(house, Decimal("-3075.36")) == "debt_payment"


def test_a_purchase_paid_through_a_savings_category_counts_as_debt(
    client: TestClient, db: Session
) -> None:
    made = client.post("/api/categories", json={"name": "Beach plot", "kind": "savings"})
    assert made.status_code == 201, made.text
    cid = made.json()["category_id"]
    account = db.scalars(select(Account)).first()
    assert account is not None
    _line(db, account.account_id, date(2026, 9, 5), "-1000.00", "PLOT INSTALLMENT", cid, "savings")
    db.commit()
    resp = client.post(
        "/api/holdings",
        json={
            "name": "Beach plot",
            "holding_class": "purchase",
            "target_amount": "6000.00",
            "installment": "1000.00",
            "category_id": cid,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    db.expire_all()
    plot = db.get(Category, cid)
    assert plot is not None and plot.kind == "debt"
    paid = db.scalar(select(Transaction).where(Transaction.description_raw == "PLOT INSTALLMENT"))
    assert paid is not None and paid.type == "debt_payment"
    assert db.scalar(
        select(ChangeLog).where(
            ChangeLog.row_id == paid.transaction_id, ChangeLog.new_value == "debt_payment"
        )
    )
    # A spending category given to a property (not a loan or purchase) is left alone.
    other = client.post("/api/categories", json={"name": "Garden", "kind": "expense"}).json()
    client.post(
        "/api/holdings",
        json={
            "name": "Garden plot",
            "holding_class": "property",
            "category_id": other["category_id"],
        },
    )
    db.expire_all()
    garden = db.get(Category, other["category_id"])
    assert garden is not None and garden.kind == "expense"
