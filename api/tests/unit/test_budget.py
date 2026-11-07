"""ADR-039: a monthly budget per group, with rollover. Synthetic data only."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.unit.test_recurring_api import USER
from tests.unit.test_shopping import _add, _cat


def _view(client: TestClient, month: str, today: str = "2026-11-10") -> dict[str, Any]:
    out = client.get(f"/api/budget/{month}", params={"today": today})
    assert out.status_code == 200, out.text
    body: dict[str, Any] = out.json()
    return body


def _group(view: dict[str, Any], name: str) -> dict[str, Any]:
    return next(g for g in view["groups"] if g["name"] == name)


def test_budget_from_the_average_pace_and_rollover(client: TestClient, db: Session) -> None:
    market, food = _cat(db, "Supermarket"), _cat(db, "Restaurants & Cafés")
    groceries, dining = market.parent_id, food.parent_id
    for m, amount in ((8, "-200"), (9, "-260"), (10, "-300")):
        _add(db, date(2026, m, 5), amount, "SUPERMAXI", market)
    _add(db, date(2026, 10, 12), "-90", "LA CLETA", food)
    _add(db, date(2026, 11, 3), "-150", "SUPERMAXI", market)
    db.commit()

    v = _view(client, "2026-11")
    assert v["has_plans"] is False and Decimal(v["day_share"]) == Decimal(10) / Decimal(30)
    g = _group(v, "Groceries")
    assert g["status"] == "none" and Decimal(g["suggested"]) == 260  # (200+260+300)/3 -> 260
    assert Decimal(v["unbudgeted"]) == 150

    started = client.post("/api/budget/2026-11/start-from-average", headers=USER)
    assert started.json() == {"added": 2}
    assert client.post("/api/budget/2026-11/start-from-average").json() == {"added": 0}
    v = _view(client, "2026-11")
    g, d = _group(v, "Groceries"), _group(v, "Dining")
    assert Decimal(g["budget"]) == 260 and Decimal(d["budget"]) == 30
    # A third of the month gone and $150 of $260 spent: ahead of pace.
    assert g["status"] == "ahead" and Decimal(g["left"]) == 110
    assert d["status"] == "on_track" and Decimal(d["spent"]) == 0
    assert Decimal(v["budgeted"]) == 290 and Decimal(v["left"]) == 140
    assert v["groups"][0]["name"] == "Groceries"  # the ones needing attention first

    # Groceries at $250 from October with rollover: October's $50 overspend comes off November.
    r = client.put(
        f"/api/budget/groups/{groceries}",
        json={"from_month": "2026-10-01", "amount": "250", "rollover": True},
        headers=USER,
    )
    assert r.status_code == 204, r.text
    g = _group(_view(client, "2026-11"), "Groceries")
    assert Decimal(g["budget"]) == 250 and g["rollover"] is True and g["since"] == "2026-10-01"
    assert Decimal(g["carried"]) == -50 and Decimal(g["available"]) == 200
    assert Decimal(g["left"]) == 50
    october = _group(_view(client, "2026-10"), "Groceries")
    assert october["status"] == "over" and Decimal(october["expected"]) == 250

    # Over budget once spending passes what's available.
    _add(db, date(2026, 11, 8), "-80", "SUPERMAXI", market)
    db.commit()
    assert _group(_view(client, "2026-11"), "Groceries")["status"] == "over"

    # Rollover off in November starts the count again; 0 = no budget from December.
    client.put(
        f"/api/budget/groups/{groceries}",
        json={"from_month": "2026-11-01", "amount": "300", "rollover": False},
    )
    g = _group(_view(client, "2026-11"), "Groceries")
    assert Decimal(g["carried"]) == 0 and Decimal(g["left"]) == 70
    client.put(f"/api/budget/groups/{dining}", json={"from_month": "2026-12-01", "amount": "0"})
    december = _view(client, "2026-12")
    assert Decimal(december["day_share"]) == 0
    assert all(x["name"] != "Dining" or x["budget"] is None for x in december["groups"])

    assert (
        client.put(
            f"/api/budget/groups/{market.category_id}",
            json={"from_month": "2026-11-01", "amount": "1"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/budget/groups/999999", json={"from_month": "2026-11-01", "amount": "1"}
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/api/budget/groups/{groceries}", json={"from_month": "2026-11-01", "amount": "-1"}
        ).status_code
        == 422
    )
    assert client.get("/api/budget/2026-13").status_code == 422


def test_deleting_a_group_moves_its_budget(client: TestClient, db: Session) -> None:
    pets = _cat(db, "Pets")
    new = client.post("/api/categories", json={"name": "Hobbies", "kind": "expense"})
    assert new.status_code == 201, new.text
    hid = new.json()["category_id"]
    client.put(f"/api/budget/groups/{hid}", json={"from_month": "2026-11-01", "amount": "40"})
    assert client.get(f"/api/categories/{hid}/uses").json()["budgets"] == 1
    out = client.delete(f"/api/categories/{hid}", params={"move_to": pets.category_id})
    assert out.status_code == 200, out.text
    g = _group(_view(client, "2026-11"), "Pets")
    assert Decimal(g["budget"]) == 40
