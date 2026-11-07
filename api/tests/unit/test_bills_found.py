"""ADR-043: bills found in the statements that no recurring item covers yet. Synthetic data."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.bills_found import pattern_of
from tests.unit.test_costs_api import USER, _account, _cat, _line

TODAY = "2026-11-05"


def _found(client: TestClient) -> list[dict[str, Any]]:
    r = client.get("/api/recurring/found", params={"today": TODAY})
    assert r.status_code == 200, r.text
    out: list[dict[str, Any]] = r.json()
    return out


def test_pattern_of() -> None:
    assert pattern_of(["NETFLIX.COM 8812", "NETFLIX.COM 9921"]) == "NETFLIX.COM"
    assert pattern_of(["CLARO PLAN 12", "CLARO PLAN 13"]) == "CLARO PLAN"
    assert pattern_of(["ABCDEF", "ABCXYZ"]) is None  # no whole word in common
    assert pattern_of(["SEGURO X", "SEGURO X"]) == "SEGURO X"
    assert pattern_of(["AB 1", "AB 2"]) is None  # too short


def test_found_then_added(client: TestClient, db: Session) -> None:
    card = _account(db, "Pichincha Mastercard Black")
    media = _cat(db, "Media")
    for i, day in enumerate((date(2026, 7, 14), date(2026, 8, 14), date(2026, 9, 15))):
        _line(db, card, day, "-15.49", f"NETFLIX.COM {8810 + i}", media)
        _line(db, card, day + timedelta(days=1), "-40.00", f"UNKNOWN GYM {i}")  # no category
    _line(db, card, date(2026, 10, 14), "-15.49", "NETFLIX.COM 8813", media)
    db.commit()

    [bill] = _found(client)
    assert (bill["merchant"], bill["every_months"], bill["amount"]) == ("NETFLIX.COM", 1, "15.49")
    assert bill["match_pattern"] == "NETFLIX.COM" and bill["due_day"] == 14
    assert bill["account_id"] == card and bill["times"] == 4 and len(bill["examples"]) == 3
    assert bill["category_path"].endswith("Media")

    made = client.post(
        "/api/recurring/templates",
        json={
            "name": "Netflix",
            "category_id": bill["category_id"],
            "type": "expense",
            "amount": bill["amount"],
            "start_month": "2026-10-01",
            "account_id": bill["account_id"],
            "match_pattern": bill["match_pattern"],
            "every_months": bill["every_months"],
            "due_day": bill["due_day"],
        },
        headers=USER,
    )
    assert made.status_code == 201, made.text
    assert _found(client) == []  # a recurring item covers it now


def test_nothing_found(client: TestClient) -> None:
    assert _found(client) == []
