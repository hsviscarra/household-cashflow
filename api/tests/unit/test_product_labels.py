"""ADR-061: grocery products by aisle, type and brand. Synthetic data only."""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import InvoiceLine, ProductRule
from app.services import invoices, product_labels
from tests.unit.test_shopping import _invoice

START = {"start": "2026-10-01", "months": "1"}


def _setup(db: Session) -> None:
    _invoice(
        db,
        date(2026, 10, 4),
        "CORPORACION FAVORITA C.A.",
        [("QSO MOZZ KIOSKO 500G", "2", "9.00"), ("PAN BLANCO", "1", "1.50")],
    )
    _invoice(
        db, date(2026, 10, 20), "CORPORACION FAVORITA C.A.", [("QSO MOZZ KIOSKO 500G", "1", "4.70")]
    )
    for ln in db.scalars(select(InvoiceLine).where(InvoiceLine.product_key == "PAN BLANCO")):
        ln.product_group, ln.group_source = None, None
    db.commit()


def test_claude_labels_then_a_person_corrects(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(db)
    assert client.post("/api/spending/groceries/label", params=START).status_code == 503
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    get_settings.cache_clear()
    sent: list[dict[str, str]] = []

    def fake(products: dict[str, str]) -> dict[str, tuple[str, str, str]]:
        sent.append(products)
        out = {}
        for pid, d in products.items():
            out[pid] = (
                ("Dairy & Eggs", "Cheese", "Kiosko") if "QSO" in d else ("Bakery", "Bread", "")
            )
        return out

    monkeypatch.setattr(product_labels, "call_claude", fake)
    try:
        r = client.post("/api/spending/groceries/label", params=START)
        assert r.status_code == 200 and r.json() == {"labeled": 2}
        assert sorted(sent[0].values()) == ["PAN BLANCO", "QSO MOZZ KIOSKO 500G"]
        assert client.post("/api/spending/groceries/label", params=START).json() == {"labeled": 0}
    finally:
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        get_settings.cache_clear()

    body = client.get("/api/spending/groceries/products", params=START).json()
    assert Decimal(body["total"]) == Decimal("15.20") and body["unlabeled"] == 0
    cheese = body["products"][0]
    assert (cheese["product_type"], cheese["brand"], cheese["times"]) == ("Cheese", "Kiosko", 2)
    assert Decimal(cheese["unit_price"]) == Decimal("4.57")
    bread = next(p for p in body["products"] if p["product_key"] == "PAN BLANCO")
    assert (bread["product_group"], bread["brand"]) == ("Bakery", None)  # no brand
    assert [t["name"] for t in body["by_brand"]] == ["Kiosko", "Unknown"]
    assert body["by_type"][0]["name"] == "Cheese" and body["by_type"][0]["products"] == 1

    put = client.put(
        "/api/spending/groceries/products",
        json={"product_key": "PAN BLANCO", "brand": "Supermaxi"},
    )
    assert put.status_code == 200 and put.json() == {"lines": 1}
    rule = db.scalar(select(ProductRule).where(ProductRule.product_key == "PAN BLANCO"))
    db.refresh(rule)
    assert rule is not None and (rule.brand, rule.product_type) == ("Supermaxi", "Bread")
    # A new invoice with the product gets the person's labels.
    lines = [
        InvoiceLine(
            invoice_id=1,
            line_no=9,
            description="PAN BLANCO",
            product_key="PAN BLANCO",
            quantity=Decimal(1),
            unit_price=Decimal(1),
            discount=Decimal(0),
            subtotal=Decimal(1),
            tax=Decimal(0),
            total=Decimal(1),
        )
    ]
    invoices.group_lines(db, lines)
    assert (lines[0].brand, lines[0].product_type, lines[0].label_source) == (
        "Supermaxi",
        "Bread",
        "confirmed",
    )
    bad = client.put(
        "/api/spending/groceries/products", json={"product_key": "PAN BLANCO", "product_group": "X"}
    )
    assert bad.status_code == 422
    missing = client.put(
        "/api/spending/groceries/products", json={"product_key": "NOPE", "brand": "A"}
    )
    assert missing.status_code == 404


def test_the_request_to_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic

    calls: list[dict[str, Any]] = []
    state = {
        "stop": "end_turn",
        "text": json.dumps(
            {
                "labels": [
                    {"product_id": "p1", "group_id": "g2", "type": " Yogurt ", "brand": "Toni"}
                ]
            }
        ),
    }

    class FakeMessages:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return SimpleNamespace(
                stop_reason=state["stop"],
                content=[SimpleNamespace(type="text", text=state["text"])],
            )

    class FakeClient:
        def __init__(self, **_kw: Any) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    assert product_labels.call_claude({"p1": "YOG TONI 1L"}) == {
        "p1": ("Dairy & Eggs", "Yogurt", "Toni")
    }
    sent = json.loads(calls[0]["messages"][0]["content"])
    assert set(sent) == {"aisles", "products"}  # descriptions only
    state["stop"] = "max_tokens"
    with pytest.raises(product_labels.SuggestError, match="cut off"):
        product_labels.call_claude({"p1": "YOG TONI 1L"})
    state["stop"], state["text"] = "end_turn", "nope"
    with pytest.raises(product_labels.SuggestError, match="could not be read"):
        product_labels.call_claude({"p1": "YOG TONI 1L"})
