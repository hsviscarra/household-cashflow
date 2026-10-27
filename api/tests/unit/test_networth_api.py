"""F14: the balance sheet. Accounts from statements, holdings from snapshots, a purchase in
progress, the workbook's balances, the series."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, BalanceSnapshot, Category, Holding, Transaction
from app.services import networth
from tests.fixtures import statements as s
from tests.fixtures.workbook import build

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _sheet(client: TestClient, as_of: str = "2026-10-27") -> dict[str, Any]:
    out: dict[str, Any] = client.get("/api/networth", params={"as_of": as_of}).json()
    return out


def _items(sheet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["name"]: i for i in sheet["items"]}


def _add(client: TestClient, **body: Any) -> int:
    resp = client.post("/api/holdings", json=body)
    assert resp.status_code == 201, resp.text
    out: int = resp.json()["holding_id"]
    return out


def test_empty(client: TestClient) -> None:
    out = _sheet(client)
    assert out["items"] == [] and out["net_worth"] == "0" and len(out["series"]) == 24


def test_workbook_balances_become_holdings_and_survive_a_reload(
    client: TestClient, db: Session
) -> None:
    files = {"file": ("Cash Flow.xlsx", build(), XLSX)}
    assert client.post("/api/history/excel/load", files=files, headers=USER).status_code == 200
    items = _items(_sheet(client))
    assert items["BIESS"]["holding_class"] == "loan" and items["BIESS"]["side"] == "liability"
    assert Decimal(items["BIESS"]["value"]) == Decimal("30000.55")
    assert items["BIESS"]["source"] == "excel" and items["BIESS"]["as_of"] == "2026-01-31"
    assert items["Remaining to pay Lender A"]["holding_class"] == "personal_loan"
    assert items["Stock Market"]["holding_class"] == "investment"
    assert items["Diners"]["holding_class"] == "card"
    # Reloading the workbook replaces its balances; they find their holdings again.
    biess = db.scalar(select(Holding).where(Holding.name == "BIESS"))
    assert biess is not None
    client.patch(f"/api/holdings/{biess.holding_id}", json={"notes": "BIESS mortgage"})
    files = {"file": ("Cash Flow.xlsx", build(lauren_jan_2026=3200), XLSX)}
    assert client.post("/api/history/excel/load", files=files, headers=USER).status_code == 200
    items = _items(_sheet(client))
    assert items["BIESS"]["notes"] == "BIESS mortgage" and items["BIESS"]["value"] is not None
    assert db.scalar(select(BalanceSnapshot).where(BalanceSnapshot.holding_id.is_(None))) is None
    assert networth.link_snapshots(db) == 0


def test_accounts_holdings_purchase_and_series(client: TestClient, db: Session) -> None:
    # A card statement (Sep 4 - Oct 3) and a bank statement (August).
    for name, data in (
        ("co.pdf", s.capitalone_full()),
        ("prod.pdf", s.produbanco_full(period="Del 01 Aug 2026 Al 31 Aug 2026", opening="900.00")),
    ):
        st = client.post("/api/statements", files=[("files", (name, data, PDF))], headers=USER)
        sid = st.json()[0]["statement"]["statement_file_id"]
        b = client.post(f"/api/statements/{sid}/read").json()
        assert b["tieout_ok"], b["checks"]
        client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)

    house = _add(client, name="Home", holding_class="property", value="100000", as_of="2025-01-01")
    _add(client, name="Car", holding_class="vehicle", value="20000", as_of="2026-09-15")
    _add(client, name="Loan", holding_class="loan", value="40000", as_of="2026-01-31")
    # A purchase in progress: 30,000 down payment in 1,000 installments, 100,000 full price;
    # 5,000 paid before the statements, then lines in its category count too.
    down = db.scalar(select(Category).where(Category.name == "Extra Debt Payoff"))
    assert down is not None
    flat = _add(
        client,
        name="Flat",
        holding_class="purchase",
        value="5000",
        as_of="2026-08-01",
        target_amount="30000",
        installment="1000",
        full_price="100000",
        category_id=down.category_id,
    )
    bank = db.scalar(select(Account).where(Account.name == "Produbanco Ahorros Hernan"))
    assert bank is not None
    db.add(
        Transaction(
            natural_key="flat-1",
            account_id=bank.account_id,
            txn_date=date(2026, 9, 5),
            cash_month=date(2026, 9, 1),
            amount=Decimal("-1000"),
            description_raw="CUOTA FLAT",
            type="savings",
            category_id=down.category_id,
            source="manual",
            status="confirmed",
        )
    )
    db.commit()

    out = _sheet(client)
    items = _items(out)
    card = items["Capital One Venture"]
    assert (card["side"], card["holding_class"], card["source"]) == (
        "liability",
        "card",
        "statement",
    )
    assert card["as_of"] == "2026-10-03" and Decimal(card["value"]) > 0
    cash = items["Produbanco Ahorros Hernan"]
    assert (cash["side"], cash["holding_class"], cash["as_of"]) == ("asset", "cash", "2026-08-31")
    flat_item = items["Flat"]
    assert Decimal(flat_item["value"]) == Decimal("6000")
    purchase = flat_item["purchase"]
    assert Decimal(purchase["remaining"]) == Decimal("24000")
    assert purchase["installments_left"] == 24
    assert Decimal(purchase["at_delivery"]) == Decimal("70000")
    assert Decimal(purchase["lines"]) == Decimal("1000")
    assert Decimal(out["commitments"]) == Decimal("94000")
    assets = Decimal(100000 + 20000 + 6000) + Decimal(cash["value"])
    assert Decimal(out["assets"]) == assets
    assert Decimal(out["liabilities"]) == Decimal(40000) + Decimal(card["value"])
    assert Decimal(out["net_worth"]) == Decimal(out["assets"]) - Decimal(out["liabilities"])
    # Items: assets first (property, vehicle, cash, purchase), then liabilities.
    assert [i["side"] for i in out["items"]] == sorted(
        [i["side"] for i in out["items"]], key=lambda x: x != "asset"
    )
    # The series values each month on its last day: the car arrives in September.
    series = {p["month"]: p for p in out["series"]}
    assert Decimal(series["2026-08-01"]["assets"]) == Decimal(100000 + 5000) + Decimal(
        cash["value"]
    )
    assert Decimal(series["2026-09-01"]["assets"]) == assets
    assert Decimal(series["2024-11-01"]["net"]) == 0

    # A new value the same day replaces the earlier one; values keep their history.
    client.post(f"/api/holdings/{house}/values", json={"as_of": "2026-10-01", "amount": "110000"})
    value = client.post(
        f"/api/holdings/{house}/values",
        json={"as_of": "2026-10-01", "amount": "105000", "notes": "appraisal"},
    ).json()
    home = _items(_sheet(client))["Home"]
    assert Decimal(home["value"]) == Decimal("105000")
    assert [(v["as_of"], v["notes"]) for v in home["history"]] == [
        ("2025-01-01", None),
        ("2026-10-01", "appraisal"),
    ]
    # Before the appraisal, the old value.
    assert Decimal(_items(_sheet(client, "2026-09-30"))["Home"]["value"]) == Decimal(100000)
    assert client.delete(f"/api/holdings/values/{value['snapshot_id']}").status_code == 204
    assert client.delete(f"/api/holdings/values/{value['snapshot_id']}").status_code == 404

    # Pause, rename, remove.
    client.patch(f"/api/holdings/{flat}", json={"is_active": False, "name": "Flat (on hold)"})
    paused = _sheet(client)
    assert _items(paused)["Flat (on hold)"]["is_active"] is False
    assert Decimal(paused["commitments"]) == 0
    assert client.delete(f"/api/holdings/{flat}").status_code == 204
    assert "Flat (on hold)" not in _items(_sheet(client))


def test_loan_payments_and_validation(client: TestClient, db: Session) -> None:
    mortgage = db.scalar(select(Category).where(Category.name == "Mortgage BIESS"))
    assert mortgage is not None
    tpl = client.post(
        "/api/recurring/templates",
        json={
            "name": "BIESS Depo",
            "category_id": mortgage.category_id,
            "type": "expense",
            "amount": "505.19",
            "start_month": "2026-08-01",
        },
    ).json()
    client.post("/api/recurring/generate", json={"month": "2026-08-01"})
    st = client.post(
        "/api/statements",
        files=[
            (
                "files",
                (
                    "p.pdf",
                    s.produbanco_full(
                        period="Del 01 Aug 2026 Al 31 Aug 2026",
                        opening="900.00",
                        lines=[("Aug 07", "1", "PAGO IESS BANCA EN LINEA", "-505.19")],
                    ),
                    PDF,
                ),
            )
        ],
        headers=USER,
    ).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    line = db.scalar(select(Transaction).where(Transaction.amount == Decimal("-505.19")))
    assert line is not None
    line.category_id = mortgage.category_id
    db.commit()
    client.post("/api/recurring/match")
    _add(
        client,
        name="BIESS",
        holding_class="loan",
        value="38000",
        as_of="2026-01-31",
        recurring_template_id=tpl["template_id"],
    )
    loan = _items(_sheet(client))["BIESS"]["loan"]
    assert Decimal(loan["monthly_payment"]) == Decimal("505.19")
    assert (Decimal(loan["paid_this_year"]), loan["payments_this_year"]) == (Decimal("505.19"), 1)

    other = _add(client, name="Watch", holding_class="other", side="asset", value="300")
    assert _items(_sheet(client))["Watch"]["side"] == "asset"
    for body, code in [
        ({"name": "Watch", "holding_class": "vehicle"}, 409),
        ({"name": " ", "holding_class": "vehicle"}, 422),
        ({"name": "Thing", "holding_class": "other"}, 422),  # owned or owed?
        ({"name": "Thing", "holding_class": "yacht"}, 422),
        ({"name": "Thing", "holding_class": "vehicle", "value": "-1"}, 422),
    ]:
        assert client.post("/api/holdings", json=body).status_code == code, body
    assert client.patch(f"/api/holdings/{other}", json={"name": "BIESS"}).status_code == 409
    assert client.patch("/api/holdings/9999", json={"notes": "x"}).status_code == 404
    assert client.delete("/api/holdings/9999").status_code == 404
    bad = client.post("/api/holdings/9999/values", json={"as_of": "2026-01-01", "amount": "1"})
    assert bad.status_code == 404
    try:
        networth.set_value(db, other, date(2026, 1, 1), Decimal(-1))
    except networth.NetWorthError as exc:
        assert exc.status == 422
    else:  # pragma: no cover
        raise AssertionError("a negative value must be refused")
