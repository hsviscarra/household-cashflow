"""ADR-033: the month in ten answers."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.unit.test_bills_api import _gen, _pay
from tests.unit.test_recurring_api import USER, _template
from tests.unit.test_shopping import _add, _cat


def _answers(
    client: TestClient, month: str, today: str = "2026-11-06"
) -> dict[int, dict[str, Any]]:
    out = client.get(f"/api/reports/{month}/answers", params={"today": today})
    assert out.status_code == 200, out.text
    return {a["n"]: a for a in out.json()}


def test_an_empty_month_still_answers(client: TestClient) -> None:
    a = _answers(client, "2026-10")
    assert sorted(a) == list(range(1, 11))
    assert a[3]["answer"] == "No bills set"
    assert a[4]["answer"] == "No purchase set"
    assert a[5]["answer"] == "No"
    assert a[6]["answer"] == "Nothing stands out"
    assert a[8]["answer"] == "$0.00"
    assert a[9]["answer"] == "—"
    assert a[10]["answer"] == "Yes" or "gap" in a[10]["answer"]
    assert _answers(client, "2026-01")[5]["answer"] == "—"  # the forecast only looks ahead
    assert client.get("/api/reports/2026-13/answers").status_code == 422


def test_a_month_with_bills_spending_a_purchase_and_held_money(
    client: TestClient, db: Session
) -> None:
    market, fees = _cat(db, "Supermarket"), _cat(db, "Bank Fees")
    for m in (7, 8, 9):
        _add(db, date(2026, m, 5), "-200", "SUPERMAXI", market)
    _add(db, date(2026, 10, 5), "-150", "SUPERMAXI", market)
    _add(db, date(2026, 10, 9), "-120", "FERRETERIA KYWI", None)
    for i in range(3):
        _add(db, date(2026, 10, 20 + i), "-0.41", "TARIFA", fees, typ="fee_interest")
    db.commit()
    rent = _template(
        client,
        name="Rent",
        category_id=market.category_id,
        amount="300",
        start_month="2026-10-01",
        due_day=1,
    )
    _template(
        client, name="Phone", category_id=market.category_id, amount="40", start_month="2026-10-01"
    )
    _gen(client, "2026-10-01")
    _pay(db, rent["template_id"], date(2026, 10, 1), "-300")
    house = client.post(
        "/api/holdings",
        json={
            "name": "New house",
            "holding_class": "purchase",
            "value": "33829",
            "as_of": "2026-10-01",
            "target_amount": "83035",
            "installment": "3075.36",
        },
    )
    assert house.status_code == 201, house.text
    person = client.post(
        "/api/people",
        json={
            "name": "Rubén",
            "new_balance": True,
            "opening_balance": "1237.09",
            "opening_as_of": "2026-10-01",
        },
        headers=USER,
    )
    assert person.status_code == 201, person.text

    a = _answers(client, "2026-10")
    # 150 + 120 + 300 rent + 1.23 fees = 571.23 against 200 in September.
    assert a[1]["answer"] == "+186% vs Sep"
    assert a[1]["tone"] == "warn" and a[1]["link"] == "/cashflow?month=2026-10"
    assert "about $200.00 a month" in a[1]["detail"]
    assert a[2]["answer"].endswith("things") and "FERRETERIA KYWI" in a[2]["detail"]
    assert a[3]["answer"] == "1 of 2" and "Phone" in a[3]["detail"]
    assert a[4]["question"] == "Are we on track for New house?"
    assert a[4]["answer"] == "41% paid" and "installments of $3,075.36 left" in a[4]["detail"]
    assert a[6]["answer"].startswith("up to $")
    assert a[7]["answer"] == "$1.23"
    assert a[8]["answer"] == "$1,237.09" and "Rubén" in a[8]["detail"]
    assert "gap" in a[10]["answer"] and "without a category" in a[10]["detail"]
    assert Decimal(a[7]["answer"].strip("$")) > 0
