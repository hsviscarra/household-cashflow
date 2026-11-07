"""ADR-036: gastos personales per person and year. Synthetic invoices and IDs only."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Category, Invoice, Transaction
from app.services import gastos
from app.services.invoices import buyer_person
from tests.fixtures.invoices import KEY, factura
from tests.unit.test_invoices import USER, card_line, upload

HERNAN_ID, LAUREN_ID = "0900000001", "0900000002"  # made up


FOOD = [
    ("LECHE ENTERA 1L", "2", "1.05", "0"),
    ("POLLO ENTERO KG", "1.250", "3.20", "0"),
    ("QUESO FRESCO", "1", "5.00", "0"),
    ("DETERGENTE POLVO", "1", "2.00", "15"),
]  # 13.10 before IVA, 11.10 of it food; 13.40 with IVA


def key(n: int) -> str:
    return KEY[:-3] + f"{n:03d}"


@pytest.fixture
def buyers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("INVOICE_BUYERS", f"Hernan:{HERNAN_ID}, Lauren:{LAUREN_ID}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_buyer_person(buyers: None) -> None:
    assert buyer_person(HERNAN_ID) == "Hernan"
    assert buyer_person(LAUREN_ID + "001") == "Lauren"  # invoiced to her RUC
    assert buyer_person("9999999999999") is None  # consumidor final
    assert buyer_person("") is None


def test_caps() -> None:
    assert gastos.cap(2026, 0, False) == Decimal("5752.60")
    assert gastos.cap(2026, 2, False) == Decimal("9039.80")
    assert gastos.cap(2026, 7, False) == Decimal("16436.00")
    assert gastos.cap(2026, 0, True) == Decimal("82180.00")
    assert gastos.cap(2019, 0, False) is None


def _cat(db: Session, name: str) -> Category:
    c = db.scalar(select(Category).where(Category.name == name))
    assert c is not None
    return c


def test_year_summary_choices_rules_and_export(
    buyers: None, client: TestClient, db: Session
) -> None:
    pharmacy_ruc, shop_ruc = "1790000000001", "1790000000002"
    upload(
        client,
        # Hernan's groceries, guessed from the products (mostly food)
        ("a.xml", factura(key=key(1), buyer=HERNAN_ID, day="05/03/2026", lines=FOOD)),
        # Lauren's pharmacy, no card line: nothing to guess from yet
        (
            "b.xml",
            factura(
                key=key(2),
                buyer=LAUREN_ID,
                day="10/04/2026",
                ruc=pharmacy_ruc,
                lines=[("TERMOMETRO DIGITAL", "1", "12.00", "15")],
            ),
        ),
        # consumidor final: nobody's
        ("c.xml", factura(key=key(3), buyer="9999999999999", day="11/04/2026", ruc=shop_ruc)),
        # another year
        ("d.xml", factura(key=key(4), buyer=HERNAN_ID, day="02/01/2025")),
    )
    s = client.get("/api/gastos/2026").json()
    assert s["canasta"] == "821.80" and s["rate"] == "0.18"
    h, lau = s["people"]
    assert h["person"] == "Hernan" and h["cap"] == "5752.60"
    food = next(c for c in h["by_category"] if c["category"] == "alimentacion")
    assert food["invoices"] == 1 and Decimal(food["amount"]) == Decimal("13.10")
    assert Decimal(h["rebate"]) == Decimal("2.36")
    assert lau["to_classify"] == 1 and s["unassigned"] == 1

    rows = client.get("/api/gastos/2026/invoices", params={"status": "to_classify"}).json()
    assert {r["issuer_ruc"] for r in rows} == {pharmacy_ruc, shop_ruc}
    nobody = client.get("/api/gastos/2026/invoices", params={"person": "none"}).json()
    assert [r["issuer_ruc"] for r in nobody] == [shop_ruc]

    # Lauren's pharmacy is Salud, for every invoice from that issuer.
    lid = next(r["invoice_id"] for r in rows if r["issuer_ruc"] == pharmacy_ruc)
    out = client.put(
        f"/api/invoices/{lid}/gastos",
        json={"category": "salud", "remember_issuer": True},
        headers=USER,
    )
    assert out.status_code == 200, out.text
    assert out.json()["category"] == "salud" and out.json()["category_source"] == "issuer"
    upload(
        client,
        (
            "e.xml",
            factura(
                key=key(5),
                buyer=LAUREN_ID,
                day="20/05/2026",
                ruc=pharmacy_ruc,
                lines=[("VITAMINA C", "1", "8.00", "0")],
            ),
        ),
    )
    lau = client.get("/api/gastos/2026").json()["people"][1]
    health = next(c for c in lau["by_category"] if c["category"] == "salud")
    assert health["invoices"] == 2 and Decimal(health["amount"]) == Decimal("20.00")

    # The consumidor final invoice is Hernan's after all, and not deductible.
    sid = nobody[0]["invoice_id"]
    out = client.put(f"/api/invoices/{sid}/gastos", json={"person": "Hernan", "category": "none"})
    assert out.json()["person_source"] == "invoice" and out.json()["category"] == "none"
    h = client.get("/api/gastos/2026").json()["people"][0]
    assert h["not_deductible"] == 1 and Decimal(h["total"]) == Decimal("13.10")
    # Clearing the person sends it back to nobody.
    client.put(f"/api/invoices/{sid}/gastos", json={"person": None})
    assert client.get("/api/gastos/2026").json()["unassigned"] == 1

    # Two cargas raise the cap; the catastrophic case raises it to 100 baskets.
    p = client.put("/api/gastos/2026/profile/Hernan", json={"cargas": 2})
    assert p.json()["cap"] == "9039.80"
    assert client.get("/api/gastos/2026").json()["people"][0]["cargas"] == 2
    p = client.put("/api/gastos/2026/profile/Hernan", json={"cargas": 2, "catastrophic": True})
    assert p.json()["cap"] == "82180.00"

    csv = client.get("/api/gastos/2026/Lauren.csv")
    assert csv.status_code == 200 and "attachment" in csv.headers["content-disposition"]
    text = csv.content.decode("utf-8-sig").splitlines()
    assert text[0].startswith("RUC,Proveedor") and text[1].startswith(f"{pharmacy_ruc},")
    assert text[1].endswith(",Salud,2,20.00,21.80")

    # Forgetting the issuer rule leaves the pharmacy without a category again.
    client.put(f"/api/invoices/{lid}/gastos", json={"category": None, "remember_issuer": True})
    lau = client.get("/api/gastos/2026").json()["people"][1]
    assert lau["to_classify"] == 2

    assert client.put("/api/invoices/999999/gastos", json={"person": "Hernan"}).status_code == 404
    assert client.put(f"/api/invoices/{sid}/gastos", json={"person": "Joint"}).status_code == 422
    assert client.put(f"/api/invoices/{sid}/gastos", json={"category": "x"}).status_code == 422
    assert client.get("/api/gastos/1999").status_code == 422
    assert client.get("/api/gastos/2024").json()["canasta"] is None


def test_person_and_category_from_the_paying_line(client: TestClient, db: Session) -> None:
    t = card_line(db, date(2026, 10, 28), Decimal("13.40"))
    t.person = "Lauren"
    t.category_id = _cat(db, "Pharmacy").category_id
    db.commit()
    upload(client, ("a.xml", factura(key=key(9), lines=FOOD)))
    inv = db.scalar(select(Invoice).where(Invoice.access_key == key(9)))
    assert inv is not None and inv.transaction_id == t.transaction_id and inv.person is None
    [row] = client.get("/api/gastos/2026/invoices").json()
    assert row["person"] == "Lauren" and row["person_source"] == "paid"
    assert row["category"] == "salud" and row["category_source"] == "paid"
    assert row["paid_as"] == "Health / Pharmacy"
    # A paying line in a category with no SRI match falls back to the products.
    paid = db.get(Transaction, t.transaction_id)
    assert paid is not None
    paid.category_id = _cat(db, "Amazon").category_id
    db.commit()
    [row] = client.get("/api/gastos/2026/invoices").json()
    assert row["category"] == "alimentacion" and row["category_source"] == "products"
