"""F15: the next three months, the lowest balance between paydays, spending alerts."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, RecurringEntry, Transaction
from app.services import projections
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
TODAY = "2026-10-20"


def _cat(db: Session, name: str) -> int:
    c = db.scalar(select(Category).where(Category.name == name))
    assert c is not None, name
    return c.category_id


def _account(db: Session, name: str) -> int:
    a = db.scalar(select(Account).where(Account.name == name))
    assert a is not None, name
    return a.account_id


def _line(
    db: Session, account_id: int, day: date, amount: str, category_id: int, n: int
) -> Transaction:
    t = Transaction(
        natural_key=f"proj-{n}",
        account_id=account_id,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=Decimal(amount),
        description_raw=f"LINE {n}",
        type="income" if Decimal(amount) > 0 else "expense",
        category_id=category_id,
        source="manual",
        status="confirmed",
    )
    db.add(t)
    return t


def _template(client: TestClient, **body: Any) -> int:
    resp = client.post("/api/recurring/templates", json={"start_month": "2026-06-01", **body})
    assert resp.status_code == 201, resp.text
    out: int = resp.json()["template_id"]
    return out


def _get(client: TestClient, today: str = TODAY) -> dict[str, Any]:
    out: dict[str, Any] = client.get("/api/projections", params={"today": today}).json()
    return out


def test_nothing_loaded(client: TestClient) -> None:
    p = _get(client)
    assert Decimal(p["start_cash"]) == 0 and p["cash_as_of"] is None
    assert [m["month"] for m in p["months"]] == ["2026-11-01", "2026-12-01", "2027-01-01"]
    assert all(Decimal(m["net"]) == 0 for m in p["months"])
    assert p["daily"][0]["day"] == TODAY and p["daily"][-1]["day"] == "2027-01-31"
    assert p["alerts"] == [] and p["next_payday"] is None


def test_three_months_cash_timing_and_alerts(client: TestClient, db: Session) -> None:
    # Cash: a bank statement closing at 2,000.00 on Sep 30.
    st = client.post(
        "/api/statements",
        files=[
            (
                "files",
                (
                    "p.pdf",
                    s.produbanco_full(
                        period="Del 01 Sep 2026 Al 30 Sep 2026", opening="2000.00", lines=[]
                    ),
                    PDF,
                ),
            )
        ],
        headers=USER,
    ).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"], b["checks"]
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    bank = _account(db, "Produbanco Ahorros Hernan")
    card = _account(db, "Capital One Venture")

    salary = _template(
        client, name="Salary", category_id=_cat(db, "Hernan"), type="income", amount="3000"
    )
    rent = _template(
        client, name="Rent", category_id=_cat(db, "Condo Fee"), type="expense", amount="1000"
    )
    for m in ("2026-09-01", "2026-11-01", "2026-12-01"):
        client.post("/api/recurring/generate", json={"month": m})
    # September's salary was paid on the 15th: it lands on the 15th from now on.
    sep_salary = db.scalar(
        select(RecurringEntry).where(
            RecurringEntry.template_id == salary, RecurringEntry.month == date(2026, 9, 1)
        )
    )
    assert sep_salary is not None
    paid = _line(db, bank, date(2026, 9, 15), "3000", _cat(db, "Hernan"), 1)
    db.flush()
    paid.recurring_entry_id = sep_salary.entry_id
    # Rent is 1,200 in November only, and doesn't happen in December.
    entries = {
        e.month: e
        for e in db.scalars(select(RecurringEntry).where(RecurringEntry.template_id == rent))
    }
    db.commit()
    client.patch(
        f"/api/recurring/entries/{entries[date(2026, 11, 1)].entry_id}", json={"amount": "1200"}
    )
    client.patch(
        f"/api/recurring/entries/{entries[date(2026, 12, 1)].entry_id}", json={"status": "skipped"}
    )

    # Variable spending from the bank, July to September: 300 a month; card purchases don't count
    # (the card payment carries them), neither do lines a recurring item paid.
    groceries = _cat(db, "Supermarket")
    n = 10
    for month in (6, 7, 8, 9):  # June is before the three months averaged for the projection
        n += 1
        _line(db, bank, date(2026, month, 10), "-300", groceries, n)
        n += 1
        _line(db, card, date(2026, month, 11), "-999", groceries, n)
    # September dining doubles its earlier average (an alert); June to August had 100 a month.
    dining = _cat(db, "Restaurants & Cafés")
    for month, amount in ((6, "-100"), (7, "-100"), (8, "-100"), (9, "-200")):
        n += 1
        _line(db, card, date(2026, month, 20), amount, dining, n)
    # A purchase in progress with two installments left, paid on the 5th.
    house = _cat(db, "Extra Debt Payoff")
    n += 1
    _line(db, bank, date(2026, 9, 5), "-500", house, n).type = "savings"
    db.commit()
    created = client.post(
        "/api/holdings",
        json={
            "name": "Flat",
            "holding_class": "purchase",
            "value": "1000",
            "as_of": "2026-10-01",
            "target_amount": "2000",
            "installment": "500",
            "category_id": house,
        },
    )
    assert created.status_code == 201

    p = _get(client)
    assert (Decimal(p["start_cash"]), p["cash_as_of"]) == (Decimal("2000"), "2026-09-30")
    assert Decimal(p["variable_per_month"]) == Decimal("300")
    assert p["average_months"] == ["2026-07-01", "2026-08-01", "2026-09-01"]
    nov, dec, jan = p["months"]
    assert (Decimal(nov["income"]), Decimal(nov["fixed"])) == (Decimal(3000), Decimal(1200))
    assert (Decimal(nov["purchases"]), Decimal(nov["variable"])) == (Decimal(500), Decimal(300))
    assert Decimal(nov["net"]) == Decimal(1000)
    assert Decimal(dec["fixed"]) == 0  # rent skipped
    assert (Decimal(jan["fixed"]), Decimal(jan["purchases"])) == (Decimal(1000), Decimal(0))
    salary_nov = next(e for e in nov["items"] if e["name"] == "Salary")
    assert salary_nov["day"] == "2026-11-15" and salary_nov["kind"] == "income"
    assert next(e for e in nov["items"] if e["name"] == "Rent")["day"] == "2026-11-01"
    assert next(e for e in nov["items"] if e["kind"] == "purchase")["day"] == "2026-11-05"

    # Day by day: October's rest has no events but variable spending; November's rent on the 1st
    # comes before the salary on the 15th.
    daily = {d["day"]: Decimal(d["balance"]) for d in p["daily"]}
    oct_left = Decimal(300) / 31 * 12  # Oct 20 to 31
    assert abs(daily["2026-10-31"] - (Decimal(2000) - oct_left)) < Decimal("0.05")
    assert Decimal(nov["end_cash"]) == daily["2026-11-30"]
    assert p["lowest"]["day"] == "2026-11-14"
    assert p["next_payday"]["day"] == "2026-11-15" and p["next_payday"]["name"] == "Salary"

    # Alerts: dining 200 against 100 (+100%); groceries is steady.
    [alert] = p["alerts"]
    assert (alert["group_name"], alert["month"]) == ("Dining", "2026-09-01")
    assert (Decimal(alert["amount"]), Decimal(alert["average"])) == (Decimal(200), Decimal(100))
    assert Decimal(alert["change"]) == Decimal(1)


def test_alert_rules(client: TestClient, db: Session) -> None:
    card = _account(db, "Capital One Venture")
    shop = _cat(db, "Clothing")
    # Small increases (under 25.00) and groups new this month raise nothing.
    for n, (month, amount) in enumerate(((7, "-50"), (8, "-50"), (9, "-70")), start=1):
        _line(db, card, date(2026, month, 3), amount, shop, n)
    _line(db, card, date(2026, 9, 4), "-500", _cat(db, "Pharmacy"), 9)
    db.commit()
    assert projections.alerts(db, date(2026, 10, 1)) == []
    assert projections.alerts(db, date(2020, 1, 1)) == []
