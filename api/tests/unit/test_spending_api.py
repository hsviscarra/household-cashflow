"""F13: one month's spending with MoM, YoY, breakdowns and drill-down."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from tests.fixtures import statements as s
from tests.fixtures.workbook import build

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _get(client: TestClient, month: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = client.get(
        "/api/spending", params={"month": month} if month else {}
    ).json()
    return out


def _statement(
    client: TestClient,
    period: str,
    lines: list[tuple[str, str, str, str]],
    opening: str = "5000.00",
) -> None:
    data = s.produbanco_full(period=period, opening=opening, lines=lines)
    st = client.post("/api/statements", files=[("files", ("p.pdf", data, PDF))], headers=USER)
    sid = st.json()[0]["statement"]["statement_file_id"]
    b = client.post(f"/api/statements/{sid}/read").json()
    assert b["tieout_ok"], b["checks"]
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)


def _cat(db: Session, name: str) -> Category:
    c = db.scalar(select(Category).where(Category.name == name))
    assert c is not None
    return c


def test_nothing_loaded(client: TestClient) -> None:
    out = _get(client)
    assert out["source"] == "none" and out["months"] == [] and out["groups"] == []
    assert Decimal(out["total"]["amount"]) == 0 and len(out["trend"]) == 12


def test_a_sheet_month_matches_the_overview_with_mom_and_yoy(client: TestClient) -> None:
    resp = client.post(
        "/api/history/excel/load", files={"file": ("Cash Flow.xlsx", build(), XLSX)}, headers=USER
    )
    assert resp.status_code == 200
    out = _get(client)  # the latest month with spending
    assert out["month"] == "2026-01-01" and out["source"] == "excel"
    overview = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    assert Decimal(out["total"]["amount"]) == Decimal(overview["2026-01-01"]["expenses"])
    # Same month last year: the 2025 sheet's January (31.40, the unlabeled Phone row).
    assert Decimal(out["total"]["last_year"]) == Decimal("31.40")
    assert Decimal(out["total"]["prev"]) == Decimal(
        overview.get("2025-12-01", {}).get("expenses", 0)
    )
    health = next(g for g in out["groups"] if g["name"] == "Health")
    assert [c["name"] for c in health["categories"]] == ["Doctors"]
    assert Decimal(health["amount"]) == Decimal("60.10")
    # Sheet months have rows, not merchants.
    assert out["merchants"] == []
    assert [t["month"] for t in out["trend"]][-1] == "2026-01-01"
    assert "2019-11-01" in out["months"] and out["months"][0] == "2026-01-01"


def test_a_statement_month_with_breakdowns_and_drill_down(client: TestClient, db: Session) -> None:
    _statement(
        client,
        "Del 01 May 2026 Al 31 May 2026",
        [("May 10", "1", "SUPERMAXI QUITO", "-80.00"), ("May 20", "2", "PAGO CONECEL", "-27.12")],
    )
    _statement(
        client,
        "Del 01 Jun 2026 Al 30 Jun 2026",
        [
            ("Jun 05", "1", "SUPERMAXI QUITO", "-100.00"),
            ("Jun 12", "2", "SUPERMAXI CUMBAYA", "-50.00"),  # same merchant, another store
            ("Jun 20", "3", "PAGO CONECEL", "-27.12"),
            ("Jun 21", "4", "DEBITO VISA", "-40.00"),  # no rule: uncategorized
            ("Jun 22", "5", "TRANSFERENCIA ENTRE CUENTAS", "-500.00"),
        ],
        opening="4892.88",  # May's closing balance
    )
    # The transfer is not spending; a refund on a card reduces groceries.
    transfer = db.scalar(select(Transaction).where(Transaction.amount == Decimal("-500")))
    assert transfer is not None
    transfer.type = "transfer"
    card = db.scalar(select(Account).where(Account.kind == "credit_card", Account.country == "US"))
    assert card is not None
    db.add(
        Transaction(
            natural_key="refund-1",
            account_id=card.account_id,
            txn_date=date(2026, 6, 25),
            cash_month=date(2026, 6, 1),
            amount=Decimal("15.00"),
            description_raw="SUPERMAXI QUITO",
            merchant="SUPERMAXI",
            type="refund",
            category_id=_cat(db, "Supermarket").category_id,
            person="Lauren",
            source="manual",
            status="confirmed",
        )
    )
    db.commit()

    out = _get(client, "2026-06-15")
    assert out["month"] == "2026-06-01" and out["source"] == "statements"
    total = out["total"]
    assert Decimal(total["amount"]) == Decimal("100") + 50 + Decimal("27.12") + 40 - 15
    assert Decimal(total["prev"]) == Decimal("107.12") and Decimal(total["last_year"]) == 0
    groceries = next(g for g in out["groups"] if g["name"] == "Groceries")
    assert (Decimal(groceries["amount"]), Decimal(groceries["prev"])) == (Decimal(135), Decimal(80))
    assert groceries["categories"][0]["name"] == "Supermarket"
    assert next(g for g in out["groups"] if g["name"] == "Uncategorized")["transactions"] == 1

    slices = {
        k: {x["key"]: Decimal(x["amount"]) for x in out[k]}
        for k in ("by_person", "by_country", "fixed")
    }
    assert slices["by_person"]["Lauren"] == Decimal(-15)
    assert set(slices["by_country"]) == {"EC", "US"} and slices["by_country"]["US"] == Decimal(-15)
    assert slices["fixed"] == {"variable": Decimal("175"), "fixed": Decimal("27.12")}
    merchants = {m["merchant"]: m for m in out["merchants"]}
    assert Decimal(merchants["SUPERMAXI"]["amount"]) == Decimal(135)
    assert merchants["SUPERMAXI"]["transactions"] == 3
    assert next(iter(merchants)) == "SUPERMAXI"

    def lines(**params: object) -> list[dict[str, Any]]:
        got: list[dict[str, Any]] = client.get(
            "/api/spending/lines", params={"month": "2026-06-01", **params}
        ).json()
        return got

    assert [ln["amount"] for ln in lines(group_id=groceries["group_id"])] == [
        "100.0000",
        "50.0000",
        "-15.0000",
    ]
    assert len(lines(category_id=groceries["categories"][0]["category_id"])) == 3
    assert len(lines(merchant="SUPERMAXI")) == 3
    assert [ln["person"] for ln in lines(person="Lauren")] == ["Lauren"]
    assert len(lines(country="EC")) == 4
    assert [(ln["merchant"], ln["description"]) for ln in lines(fixed=True)] == [
        ("CONECEL", "PAGO CONECEL")
    ]
    assert lines(fixed=True)[0]["account_name"] == "Produbanco Ahorros Hernan"
