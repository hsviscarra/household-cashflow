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
    # November's salary arrived on Oct 15, the month before (ADR-084); December's arrives Nov 15.
    assert salary_nov["day"] == "2026-10-15" and salary_nov["kind"] == "income"
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


def test_accounts_floor_held_horizon_and_what_ifs(client: TestClient, db: Session) -> None:
    """ADR-033: each account day by day with its floor, money held for others left out, 1 or 12
    months, a longer average and what-ifs against the base."""
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
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    bank = _account(db, "Produbanco Ahorros Hernan")
    _template(
        client,
        name="House",
        category_id=_cat(db, "Condo Fee"),
        type="expense",
        amount="1500",
        account_id=bank,
        due_day=30,
    )
    # Rubén's money: 500 held in the bank.
    person = client.post(
        "/api/people",
        json={
            "name": "Rubén",
            "new_balance": True,
            "opening_balance": "500",
            "opening_as_of": "2026-10-01",
        },
    )
    assert person.status_code == 201, person.text

    def get(**params: object) -> dict[str, Any]:
        out: dict[str, Any] = client.get(
            "/api/projections", params={"today": TODAY, **params}
        ).json()
        return out

    p = get(floor="1000")
    assert Decimal(p["held"]) == 500 and p["include_held"] is False
    assert Decimal(p["start_cash"]) == 1500  # 2,000 less 500 held for Rubén
    assert Decimal(get(include_held="true")["start_cash"]) == 2000
    [acct] = p["accounts"]
    assert acct["name"] == "Produbanco Ahorros Hernan" and Decimal(acct["start"]) == 2000
    assert acct["under_floor"] == "2026-10-30"  # 2,000 - 1,500 = 500, under 1,000
    # Oct 30, Nov 30, Dec 30 and Jan 30: 2,000 - 4 x 1,500 = -4,000; 5,000 brings it to 1,000.
    assert Decimal(acct["lowest"]["balance"]) == Decimal(-4000)
    assert Decimal(acct["move"]) == 5000
    assert p["first_short"] == "2026-10-30"
    assert [m["month"] for m in get(horizon="1")["months"]] == ["2026-11-01"]
    assert len(get(horizon="12")["months"]) == 12
    assert get(average_over="6")["average_over"] == 6
    assert client.get("/api/projections", params={"horizon": 2}).status_code == 422

    # What if: 1,000 a month in from the 1st, and a one-off 200 out.
    body = {
        "floor": "1000",
        "changes": [
            {"name": "From Hernan", "amount": "1000", "day": 1, "account_id": bank},
            {"name": "Repair", "amount": "-200", "every": "once", "on": "2026-11-10"},
            {"name": "Too late", "amount": "-5", "every": "once", "on": "2030-01-01"},
        ],
    }
    w = client.post("/api/projections/scenario", params={"today": TODAY}, json=body).json()
    assert w["base"]["first_short"] == "2026-10-30"
    assert Decimal(w["end_cash"]) - Decimal(w["base"]["end_cash"]) == Decimal(3000 - 200)
    nov = w["months"][0]
    assert {e["name"] for e in nov["items"]} >= {"From Hernan", "Repair", "House"}
    assert Decimal(nov["income"]) == 1000
    assert Decimal(w["accounts"][0]["lowest"]["balance"]) == Decimal(-1000)  # 3,000 in, before
    plain = client.post("/api/projections/scenario", params={"today": TODAY}, json={}).json()
    assert plain["base"] is None


def _history(db: Session, pay_doctor_with: str) -> None:
    """Three years of everyday spending: about 100 of groceries a month from the bank, and 600
    at the doctor every August."""
    bank = _account(db, "Produbanco Ahorros Hernan")
    doctor_account = _account(db, pay_doctor_with)
    groceries, doctors = _cat(db, "Supermarket"), _cat(db, "Doctors")
    n = 1000
    for year in (2024, 2025, 2026):
        for month in range(1, 13):
            if (year, month) >= (2026, 10):
                break
            # 2024 and 2025 swing by 20 in opposite months: variation, but not a season.
            swing = 0 if year == 2026 else (20 if (month + year) % 2 else -20)
            _line(db, bank, date(year, month, 5), str(-(100 + swing)), groceries, n := n + 1)
            if month == 8:
                _line(db, doctor_account, date(year, 8, 10), "-600", doctors, n := n + 1)
    db.commit()


def _year_ahead(client: TestClient, **params: Any) -> dict[str, Any]:
    out: dict[str, Any] = client.get(
        "/api/projections", params={"today": TODAY, "horizon": 12, **params}
    ).json()
    return out


def test_seasons_and_the_likely_range(client: TestClient, db: Session) -> None:
    """ADR-096: August's doctor is forecast in August, and cash has a range around it."""
    _history(db, "Produbanco Ahorros Hernan")
    p = _year_ahead(client)
    assert p["seasons"] is True and p["seasonal_groups"] == 1
    # The plain average of July to September says 300 a month; it is 100, and 700 in August.
    assert Decimal(p["variable_per_month"]) == Decimal("300.00")
    everyday = {m["month"]: Decimal(m["variable"]) for m in p["months"]}
    assert everyday["2026-11-01"] == Decimal("100.00") and everyday["2027-08-01"] == Decimal(700)
    assert sum(everyday.values()) == Decimal(1800)  # a year: 12 x 100 and one 600
    august = next(m for m in p["months"] if m["month"] == "2027-08-01")
    assert august["seasonal"] == [{"group_name": "Health", "extra": "550.00"}]
    assert p["months"][0]["seasonal"] == []

    # The range: built from the swings of 20, around the expected cash, wider further out.
    assert len(p["band"]) == len(p["daily"]) and p["band"][0]["day"] == TODAY
    first, last = p["months"][0], p["months"][-1]
    for m in (first, last):
        assert Decimal(m["end_cash_low"]) < Decimal(m["end_cash"]) < Decimal(m["end_cash_high"])
    width = lambda m: Decimal(m["end_cash_high"]) - Decimal(m["end_cash_low"])  # noqa: E731
    assert width(last) > width(first)
    assert Decimal(p["band"][-1]["low"]) == Decimal(last["end_cash_low"])
    # No money in the bank and only spending ahead: under a floor of zero for sure.
    assert Decimal(p["chance_under_floor"]) == 1

    # Without seasons every month is the average, and August's 600 counts as a surprise.
    flat = _year_ahead(client, seasons=False)
    assert flat["seasons"] is False and flat["seasonal_groups"] == 0
    assert {Decimal(m["variable"]) for m in flat["months"]} == {Decimal("300.00")}
    assert all(m["seasonal"] == [] for m in flat["months"])
    assert width(flat["months"][-1]) > width(last)

    # What-ifs keep the choice.
    what_if = client.post(
        "/api/projections/scenario",
        params={"today": TODAY},
        json={"horizon": 12, "seasons": False, "changes": []},
    ).json()
    assert what_if["seasons"] is False


def test_a_season_on_a_card_is_paid_the_month_after(client: TestClient, db: Session) -> None:
    _history(db, "Capital One Venture")
    p = _year_ahead(client)
    everyday = {m["month"]: Decimal(m["variable"]) for m in p["months"]}
    # The bank pays 100 of groceries every month. The doctor goes on the card: what August
    # spends over a usual month (600 less 50) leaves the bank in September, with the card.
    assert everyday["2027-08-01"] == Decimal("100.00")
    assert everyday["2027-09-01"] == Decimal("650.00")
    assert everyday["2026-11-01"] == Decimal("100.00")


def test_too_little_history_has_no_range(client: TestClient) -> None:
    p = _get(client)
    assert p["band"] == [] and p["chance_under_floor"] is None and p["seasonal_groups"] == 0
    assert p["months"][0]["end_cash_low"] is None
