"""ADR-059: groceries, from the statements and the supermarkets' invoices. Synthetic data."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InvoiceLine
from app.services import groceries
from tests.unit.test_shopping import _add, _cat, _invoice


def test_month_of_groceries(client: TestClient, db: Session) -> None:
    market, fees = _cat(db, "Supermarket"), _cat(db, "Bank Fees")
    for month in (7, 8, 9):
        _add(db, date(2026, month, 5), "-200", "SUPERMAXI", market)
    paid = _add(db, date(2026, 10, 4), "-9.00", "SUPERMAXI", market)
    _add(db, date(2026, 10, 18), "-150.00", "MEGAMAXI", market)  # its invoice hasn't come
    _add(db, date(2026, 10, 20), "-3.00", "FEE", fees)
    _invoice(db, date(2026, 9, 5), "CORPORACION FAVORITA C.A.", [("Leche 1L", "2", "2.00")])
    _invoice(
        db,
        date(2026, 10, 4),
        "CORPORACION FAVORITA C.A.",
        [("Leche 1L", "2", "2.40"), ("Queso", "1", "6.60")],
        paid,
    )
    _invoice(db, date(2026, 10, 9), "FUNDACION EDUCACIONAL", [("PENSION OCTUBRE", "1", "719")])
    for ln in db.scalars(select(InvoiceLine).where(InvoiceLine.product_key == "PENSION OCTUBRE")):
        ln.product_group = None  # not food
    db.commit()

    body = client.get("/api/spending/groceries", params={"month": "2026-10-01"}).json()
    assert Decimal(body["spent"]) == Decimal("159.00")
    assert Decimal(body["usual"]) == Decimal("200.00")
    assert Decimal(body["invoiced"]) == Decimal("9.00")  # the school's invoice isn't groceries
    assert [p["month"] for p in body["trend"]][-1] == "2026-10-01" and len(body["trend"]) == 6
    assert [s["name"] for s in body["stores"]] == ["CORPORACION FAVORITA C.A."]
    dairy = body["aisles"][0]
    assert dairy["name"] == "Dairy & Eggs" and Decimal(dairy["amount"]) == Decimal("9.00")
    assert Decimal(dairy["usual"]) == Decimal("2.00")
    milk = next(p for p in body["products"] if p["product_key"] == "LECHE 1L")
    assert Decimal(milk["unit_price"]) == Decimal("1.20") and Decimal(milk["change"]) > 0
    assert [(c["merchant"], Decimal(c["amount"])) for c in body["missing"]] == [
        ("MEGAMAXI", Decimal("150.00"))
    ]


def test_store_names() -> None:
    assert groceries.is_store("CORPORACION FAVORITA C.A.")
    assert groceries.is_store("Corporacion El Rosado S.A.")
    assert groceries.is_store("TIENDAS INDUSTRIALES ASOCIADAS TIA S.A.")
    assert not groceries.is_store("FYBECA BATAN")
    assert not groceries.is_store("BAKI S.A.")  # not a word match for AKI


def test_no_groceries_at_all(client: TestClient) -> None:
    body = client.get("/api/spending/groceries", params={"month": "2026-10-01"}).json()
    assert Decimal(body["spent"]) == 0 and body["aisles"] == [] and body["missing"] == []
