"""ADR-047: one To do list. Synthetic data only."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.unit.test_classify_api import _cat, loaded  # noqa: F401
from tests.unit.test_inbox_api import TRANSFER

TODAY = {"today": "2026-09-05"}


def _todo(client: TestClient) -> dict[str, Any]:
    r = client.get("/api/todo", params=TODAY)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def _section(body: dict[str, Any], key: str) -> dict[str, Any] | None:
    return next((s for s in body["sections"] if s["key"] == key), None)


def test_old_values(client: TestClient) -> None:
    old = {"name": "Fondo", "holding_class": "cash", "value": "500", "as_of": "2026-05-31"}
    assert client.post("/api/holdings", json=old).status_code == 201
    fresh = {"name": "House", "holding_class": "property", "value": "9", "as_of": "2026-05-31"}
    assert client.post("/api/holdings", json=fresh).status_code == 201
    body = _todo(client)
    values = _section(body, "values")
    assert values is not None
    names = {t["title"]: t for t in values["tasks"]}
    assert "Fondo" in names and "House" not in names  # property is yearly
    assert names["Fondo"]["kind"] == "stale" and "97 days old" in names["Fondo"]["detail"]
    assert body["total"] == sum(s["count"] for s in body["sections"])


def test_categorize_and_who(loaded: TestClient, db: Session) -> None:  # noqa: F811
    body = _todo(loaded)
    cat = _section(body, "categorize")
    assert cat is not None and cat["count"] >= 2
    first = cat["tasks"][0]
    assert first["kind"] == "categorize" and first["data"]["transaction_ids"]
    assert body["total"] == sum(s["count"] for s in body["sections"])

    # Resolving a merchant takes it off the list.
    office = _cat(db, "Office Rent")
    key = first["data"]["merchant_key"]
    out = loaded.post("/api/review/resolve", json={"merchant_key": key, "category_id": office})
    assert out.status_code == 200, out.text
    keys = {
        t["data"]["merchant_key"]
        for t in (_section(_todo(loaded), "categorize") or {"tasks": []})["tasks"]
    }
    assert key not in keys

    # A transfer that doesn't say who: given a person or an income category, it's done.
    who = _section(_todo(loaded), "who")
    assert who is not None
    task = next(t for t in who["tasks"] if t["title"].startswith(TRANSFER))
    tid = task["data"]["transaction_id"]
    # A debt category (a house installment) explains it too (it came back, 2026-11-10).
    house = _cat(db, "Housing/New house")
    assert loaded.patch(f"/api/transactions/{tid}", json={"category_id": house}).status_code == 200
    who = _section(_todo(loaded), "who") or {"tasks": []}
    assert tid not in {t["data"]["transaction_id"] for t in who["tasks"]}
    salary = _cat(db, "Salary")
    assert loaded.patch(f"/api/transactions/{tid}", json={"category_id": salary}).status_code == 200
    who = _section(_todo(loaded), "who") or {"tasks": []}
    assert tid not in {t["data"]["transaction_id"] for t in who["tasks"]}
