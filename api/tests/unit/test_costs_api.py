"""F14: recurring charges (subscriptions) and the cost of debt."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from app.services import subscriptions
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
TODAY = "2026-10-27"


def _cat(db: Session, name: str) -> int:
    c = db.scalar(select(Category).where(Category.name == name))
    assert c is not None, name
    return c.category_id


def _account(db: Session, name: str) -> int:
    a = db.scalar(select(Account).where(Account.name == name))
    assert a is not None, name
    return a.account_id


def _line(
    db: Session,
    account_id: int,
    day: date,
    amount: str,
    description: str,
    category_id: int | None = None,
    type_: str = "expense",
) -> None:
    db.add(
        Transaction(
            natural_key=f"{account_id}|{day}|{description}|{amount}",
            account_id=account_id,
            txn_date=day,
            cash_month=day.replace(day=1),
            amount=Decimal(amount),
            description_raw=description,
            type=type_,
            category_id=category_id,
            source="manual",
            status="confirmed",
        )
    )


def _subs(client: TestClient) -> dict[str, Any]:
    out: dict[str, Any] = client.get("/api/subscriptions", params={"today": TODAY}).json()
    return out


def test_weekly_monthly_possible_and_stopped(client: TestClient, db: Session) -> None:
    card = _account(db, "Pichincha Mastercard Black")
    other = _account(db, "Capital One Venture")
    apps, media = _cat(db, "Apps"), _cat(db, "Media")
    start = date(2026, 9, 1)
    for i in range(4):  # weekly app billing
        _line(db, card, start + timedelta(days=7 * i), "-9.99", f"GOOGLE *Sample App M {i}", apps)
    for i, amount in enumerate(("-12.99", "-12.99", "-13.49")):  # monthly, price went up a bit
        _line(
            db,
            other,
            date(2026, 7, 15) + timedelta(days=30 * i),
            amount,
            "STREAMFLIX 4455667",
            media,
        )
    for i in range(2):  # monthly but stopped: the card's lines go on two months later
        _line(db, other, date(2026, 5, 3) + timedelta(days=31 * i), "-5.00", "OLDAPP*SUB", media)
    _line(db, other, date(2026, 9, 1), "-80.00", "BETTERFIT APP", apps)  # seen once
    for i, amount in enumerate(("-10", "-90")):  # monthly gaps but very different amounts
        _line(db, other, date(2026, 8, 2) + timedelta(days=30 * i), amount, "CORNER SHOP")
    for i in range(3):  # a monthly fee is a cost of debt, not a subscription
        _line(
            db,
            card,
            date(2026, 7, 5) + timedelta(days=30 * i),
            "-1.50",
            "COMISION",
            _cat(db, "Bank Fees"),
        )
    _line(db, card, date(2026, 9, 3), "25.00", "REFUND APP", apps)  # money back: ignored
    db.commit()

    out = _subs(client)
    found = {x["merchant"]: x for x in out["subscriptions"]}
    weekly = found["GOOGLE *SAMPLE APP M"]
    assert (weekly["cadence"], weekly["active"], len(weekly["charges"])) == ("weekly", True, 4)
    assert Decimal(weekly["monthly_cost"]) == Decimal("43.29")  # 9.99 x 52 / 12
    assert weekly["next_expected"] == "2026-09-29"
    assert weekly["accounts"] == ["Pichincha Mastercard Black"]
    monthly = found["STREAMFLIX"]
    assert (monthly["cadence"], Decimal(monthly["typical"])) == ("monthly", Decimal("12.99"))
    assert monthly["category_path"] == "Subscriptions & Software / Media"
    assert found["OLDAPP*SUB"]["active"] is False
    assert found["BETTERFIT APP"]["cadence"] == "possible"
    assert "CORNER SHOP" not in found and "COMISION" not in found
    # Weekly first, then monthly; the totals count active, steady ones only.
    assert [x["cadence"] for x in out["subscriptions"]][:2] == ["weekly", "monthly"]
    assert Decimal(out["weekly_monthly_cost"]) == Decimal("43.29")
    assert Decimal(out["monthly_cost"]) == Decimal("43.29") + Decimal("12.99")


def test_cadences() -> None:
    d = date(2026, 1, 1)
    assert subscriptions.cadence_of([d]) is None
    assert subscriptions.cadence_of([d, d + timedelta(days=91)]) == ("quarterly", 91)
    assert subscriptions.cadence_of([d, d + timedelta(days=365)]) == ("yearly", 365)
    assert subscriptions.cadence_of([d, d + timedelta(days=7), d + timedelta(days=40)]) is None


def test_nothing_loaded(client: TestClient) -> None:
    assert _subs(client) == {"monthly_cost": "0", "weekly_monthly_cost": "0", "subscriptions": []}
    debt = client.get("/api/debt", params={"today": TODAY}).json()
    assert debt["accounts"] == [] and debt["year"] == 2026 and debt["through"] == "2026-10-01"


def test_interest_and_fees_per_account_year_to_date(client: TestClient, db: Session) -> None:
    # Capital One: the statement's interest charge (10.00) and its balance.
    st = client.post(
        "/api/statements", files=[("files", ("co.pdf", s.capitalone_full(), PDF))], headers=USER
    ).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"], b["checks"]
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    # Pichincha: interest, interest earned on a credit balance, SOLCA and the digital tax; a
    # bank fee on Produbanco; last year's interest counts in the last 12 months only.
    card = _account(db, "Pichincha Mastercard Black")
    bank = _account(db, "Produbanco Ahorros Hernan")
    interest = _cat(db, "Credit Card Interest")
    _line(db, card, date(2026, 7, 12), "-0.56", "INT. FINANCIAMIENTO", interest, "fee_interest")
    _line(db, card, date(2026, 7, 12), "0.03", "INTERESES SALDO A FAVOR", interest, "fee_interest")
    _line(db, card, date(2026, 7, 12), "-0.02", "CONT_FIN_SOLCA", _cat(db, "SOLCA Contribution"))
    _line(
        db,
        card,
        date(2026, 8, 14),
        "-1.27",
        "RET IVA SERV DIGITAL",
        _cat(db, "Taxes on Digital Services"),
    )
    _line(db, card, date(2025, 12, 12), "-4.00", "INT. FINANCIAMIENTO", interest, "fee_interest")
    _line(db, bank, date(2026, 9, 30), "-0.35", "COMISION", _cat(db, "Bank Fees"))
    db.commit()

    d = client.get("/api/debt", params={"today": TODAY}).json()
    assert (d["year"], d["through"], d["years"]) == (2026, "2026-10-01", [2026, 2025])
    assert len(d["months"]) == 12 and d["months"][-1] == "2026-10-01"
    accounts = {a["name"]: a for a in d["accounts"]}
    co = accounts["Capital One Venture"]
    assert (Decimal(co["interest"]), Decimal(co["fees"])) == (Decimal("10"), Decimal(0))
    assert co["balance_date"] == "2026-10-03" and Decimal(co["balance"]) > 0
    pich = accounts["Pichincha Mastercard Black"]
    assert Decimal(pich["interest"]) == Decimal("0.53")
    assert Decimal(pich["fees"]) == Decimal("1.29")
    assert Decimal(pich["last_12"]) == Decimal("5.82")
    assert pich["by_category"] == {
        "Credit Card Interest": "0.5300",
        "SOLCA Contribution": "0.0200",
        "Taxes on Digital Services": "1.2700",
    }
    assert pich["by_month"]["2025-12-01"] == "4.0000"
    assert accounts["Produbanco Ahorros Hernan"]["balance"] is None  # a bank: no debt balance
    assert Decimal(d["interest"]) == Decimal("10.53") and Decimal(d["fees"]) == Decimal("1.64")
    assert d["accounts"][0]["name"] == "Capital One Venture"  # the most expensive first

    last_year = client.get("/api/debt", params={"year": 2025, "today": TODAY}).json()
    assert last_year["through"] == "2025-12-01"
    assert Decimal(last_year["interest"]) == Decimal("4")
    assert client.get("/api/debt", params={"year": 1900}).status_code == 422
