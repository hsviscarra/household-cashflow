"""ADR-040: saving goals. Synthetic data only."""

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.services.goals import months_between
from tests.unit.test_recurring_api import USER

TODAY = {"today": "2026-11-07"}


def _goals(client: TestClient) -> dict[str, Any]:
    out = client.get("/api/goals", params=TODAY)
    assert out.status_code == 200, out.text
    body: dict[str, Any] = out.json()
    return body


def _holding(client: TestClient, **body: Any) -> dict[str, Any]:
    r = client.post("/api/holdings", json=body)
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def test_months_between() -> None:
    from datetime import date

    assert months_between(date(2026, 11, 1), date(2026, 12, 31)) == 2
    assert months_between(date(2026, 11, 1), date(2027, 11, 1)) == 13
    assert months_between(date(2026, 11, 1), date(2026, 10, 1)) == 0


def test_goals_pace_links_and_changes(client: TestClient) -> None:
    fund = _holding(
        client, name="Fondo emergencia", holding_class="cash", value="3000", as_of="2026-10-31"
    )
    house = _holding(
        client,
        name="New house",
        holding_class="purchase",
        value="33829",
        as_of="2026-10-01",
        target_amount="83035",
        installment="3075.36",
    )
    places = {p["key"]: p for p in _goals(client)["places"]}
    fund_key, house_key = f"holding-{fund['holding_id']}", f"holding-{house['holding_id']}"
    assert Decimal(places[fund_key]["value"]) == 3000
    assert Decimal(places[house_key]["value"]) == 33829  # what's paid

    # Emergency fund: $9,000 by the end of next October (12 months: Nov..Oct), $400 planned.
    r = client.post(
        "/api/goals",
        params=TODAY,
        json={
            "name": "Emergency fund",
            "target_amount": "9000",
            "target_date": "2027-10-31",
            "item_key": fund_key,
            "monthly_amount": "400",
        },
        headers=USER,
    )
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["place_name"] == "Fondo emergencia" and Decimal(g["current"]) == 3000
    assert g["months_left"] == 12 and Decimal(g["needed_monthly"]) == 500
    assert Decimal(g["projected"]) == 7800 and g["status"] == "behind"
    assert Decimal(g["share"]) == Decimal("0.3333")

    # $500 a month gets it there.
    g = client.patch(
        f"/api/goals/{g['goal_id']}", params=TODAY, json={"monthly_amount": "500"}
    ).json()
    assert g["status"] == "on_pace"

    # A trip with money typed by hand and no date; then reached.
    trip = client.post(
        "/api/goals",
        params=TODAY,
        json={"name": "Galápagos", "target_amount": "2500", "saved_amount": "600"},
    ).json()
    assert (
        trip["status"] == "open"
        and trip["needed_monthly"] is None
        and Decimal(trip["left"]) == 1900
    )
    trip = client.patch(
        f"/api/goals/{trip['goal_id']}", params=TODAY, json={"saved_amount": "2600"}
    ).json()
    assert (
        trip["status"] == "reached" and Decimal(trip["left"]) == 0 and Decimal(trip["share"]) == 1
    )

    # A date already past and not reached is late; clearing the date opens it again.
    late = client.post(
        "/api/goals",
        params=TODAY,
        json={"name": "Car", "target_amount": "5000", "target_date": "2026-10-01"},
    ).json()
    assert late["status"] == "late"
    late = client.patch(
        f"/api/goals/{late['goal_id']}", params=TODAY, json={"target_date": None}
    ).json()
    assert late["status"] == "open"

    # The house goal follows what's paid on the purchase.
    h = client.post(
        "/api/goals",
        params=TODAY,
        json={"name": "House down payment", "target_amount": "83035", "item_key": house_key},
    ).json()
    assert Decimal(h["current"]) == 33829

    # Inactive goals go last.
    client.patch(f"/api/goals/{late['goal_id']}", json={"is_active": False})
    names = [x["name"] for x in _goals(client)["goals"]]
    assert names[-1] == "Car"

    assert (
        client.post(
            "/api/goals", json={"name": "X", "target_amount": "10", "item_key": "account-999"}
        ).status_code
        == 422
    )
    assert client.post("/api/goals", json={"name": "X", "target_amount": "0"}).status_code == 422
    assert client.patch("/api/goals/9999", json={"name": "Y"}).status_code == 404
    assert client.delete(f"/api/goals/{late['goal_id']}").status_code == 204
    assert client.delete(f"/api/goals/{late['goal_id']}").status_code == 404
