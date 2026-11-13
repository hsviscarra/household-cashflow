"""ADR-097: the savings rate, what the goals need, what is safe to spend, and the debts."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AppSetting, Category, Transaction
from app.services import debt, loans, measures, networth, savings

TODAY = "2026-10-20"
DAY = date(2026, 10, 20)


def _cat(db: Session, name: str) -> int:
    c = db.scalar(select(Category).where(Category.name == name))
    assert c is not None, name
    return c.category_id


def _line(db: Session, day: date, amount: str, category: str, type_: str, n: int) -> None:
    bank = db.scalar(select(Account).where(Account.name == "Produbanco Ahorros Hernan"))
    assert bank is not None
    db.add(
        Transaction(
            natural_key=f"sav-{n}",
            account_id=bank.account_id,
            txn_date=day,
            cash_month=day.replace(day=1),
            amount=Decimal(amount),
            description_raw=f"LINE {n}",
            type=type_,
            category_id=_cat(db, category),
            source="manual",
            status="confirmed",
        )
    )


def _get(client: TestClient, **params: Any) -> dict[str, Any]:
    resp = client.get("/api/savings", params={"today": TODAY, **params})
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _holding(client: TestClient, name: str, holding_class: str, value: str) -> str:
    resp = client.post(
        "/api/holdings",
        json={"name": name, "holding_class": holding_class, "value": value, "as_of": "2026-10-01"},
    )
    assert resp.status_code == 201, resp.text
    return f"holding-{resp.json()['holding_id']}"


def test_nothing_loaded(client: TestClient) -> None:
    out = _get(client)
    assert out["rate_12"] is None and out["debts"] == [] and out["payoff"] is None
    assert out["goals"]["goals"] == [] and Decimal(out["goals"]["needed"]) == 0
    safe = out["safe"]
    assert Decimal(safe["amount"]) == 0 and safe["days_left"] == 12  # Oct 20 to 31


def test_rate_goals_and_safe_to_spend(client: TestClient, db: Session) -> None:
    # September: 3,000 in, 1,000 spent. October so far: 3,000 in, 400 spent, 200 into savings.
    _line(db, date(2026, 9, 2), "3000", "Hernan", "income", 1)
    _line(db, date(2026, 9, 9), "-1000", "Supermarket", "expense", 2)
    _line(db, date(2026, 10, 2), "3000", "Hernan", "income", 3)
    _line(db, date(2026, 10, 5), "-400", "Supermarket", "expense", 4)
    _line(db, date(2026, 10, 6), "-200", "Extra Debt Payoff", "savings", 5)
    _line(db, date(2026, 10, 28), "-999", "Supermarket", "expense", 6)  # after today: not yet
    db.commit()
    # Rent of 1,000 is due on the 25th; a trip of 1,200 by January with 300 a month planned.
    made = client.post(
        "/api/recurring/templates",
        json={
            "name": "Rent",
            "category_id": _cat(db, "Condo Fee"),
            "type": "expense",
            "amount": "1000",
            "due_day": 25,
            "start_month": "2026-06-01",
        },
    )
    assert made.status_code == 201, made.text
    client.post("/api/recurring/generate", json={"month": "2026-10-01"})
    goal = client.post(
        "/api/goals",
        params={"today": TODAY},
        json={
            "name": "Trip",
            "target_amount": "1200",
            "target_date": "2027-01-31",
            "monthly_amount": "250",
        },
    )
    assert goal.status_code == 201, goal.text

    out = _get(client)
    months = {m["month"]: m for m in out["months"]}
    sep, october = months["2026-09-01"], months["2026-10-01"]
    assert (Decimal(sep["kept"]), Decimal(sep["rate"])) == (Decimal(2000), Decimal("0.6667"))
    assert october["running"] is True and Decimal(october["rate"]) == Decimal("0.8667")
    # The rate of the year leaves the running month out: only September has money in.
    assert Decimal(out["rate_12"]) == Decimal("0.6667")

    plan = out["goals"]
    # 1,200 in four months (October to January) is 300 a month; 250 is planned, 200 is in.
    assert (Decimal(plan["needed"]), Decimal(plan["planned"])) == (Decimal(300), Decimal(250))
    assert (Decimal(plan["saved"]), Decimal(plan["to_go"])) == (Decimal(200), Decimal(50))
    assert Decimal(plan["short"]) == Decimal(50) and plan["goals"][0]["status"] == "behind"

    safe = out["safe"]
    # 3,000 in, less 400 spent and 200 set aside; then rent (1,000) and the goal's 50 to go.
    assert Decimal(safe["left_so_far"]) == Decimal(2400)
    assert (Decimal(safe["income_to_come"]), Decimal(safe["bills_to_come"])) == (0, Decimal(1000))
    assert Decimal(safe["goals_to_go"]) == Decimal(50)
    assert Decimal(safe["amount"]) == Decimal(1350)
    assert Decimal(safe["a_day"]) == Decimal("112.50")  # over 12 days
    assert client.get("/api/savings/safe-to-spend", params={"today": TODAY}).json() == safe

    # ADR-096: the months' spending in one query is the same as month by month.
    months = [date(2026, 9, 1), date(2026, 10, 1), date(2026, 8, 1)]
    assert measures.spent_by_month(db, months) == {
        date(2026, 9, 1): measures.window(db, date(2026, 9, 1)).spent,
        date(2026, 10, 1): measures.window(db, date(2026, 10, 1)).spent,
    }
    assert measures.spent_by_month(db, months)[date(2026, 10, 1)] == Decimal(1399)


def test_debts_their_terms_and_the_two_orders(client: TestClient, db: Session) -> None:
    car = _holding(client, "Car loan", "loan", "5000")
    family = _holding(client, "Family loan", "personal_loan", "1000")
    card = _holding(client, "Store card", "card", "2000")
    _holding(client, "Home", "property", "90000")  # not a debt

    out = _get(client)
    by_key = {d["key"]: d for d in out["debts"]}
    assert set(by_key) == {car, family, card}
    # Nothing is known about the loans yet. A card isn't planned at all until its rate is
    # typed: its balance may just be this month's purchases.
    assert by_key[car]["planned"] is False and by_key[car]["rate"] is None
    assert (by_key[card]["kind"], by_key[card]["minimum"], by_key[card]["rate"]) == (
        "card",
        None,
        None,
    )
    assert out["payoff"] is None

    def put(key: str, **body: Any) -> int:
        return client.put(
            f"/api/savings/debts/{key}", params={"today": TODAY}, json=body
        ).status_code

    assert put(car, rate="0.24", minimum="150") == 204
    assert put(family, rate="0.06", minimum="50") == 204
    assert put("holding-999", rate="0.1", minimum="10") == 404
    assert put(car, rate="3") == 422 and put(car, minimum="-1") == 422
    # With its rate typed, the card is carried: its payment is assumed at 3% until typed too.
    assert put(card, rate="0.18") == 204
    typed = {d["key"]: d for d in _get(client)["debts"]}[card]
    assert (typed["minimum"], typed["minimum_from"], typed["planned"]) == ("60.00", "assumed", True)
    assert put(card) == 204

    out = _get(client, extra="200")
    by_key = {d["key"]: d for d in out["debts"]}
    assert by_key[car]["planned"] and by_key[car]["rate_from"] == "typed"
    assert out["debts"][0]["key"] == car  # the highest rate first
    plans = out["payoff"]
    assert Decimal(plans["extra"]) == Decimal(200)
    # The smallest first closes the family loan first; the highest rate first, the car loan.
    assert plans["snowball"]["order"] == [family, car]
    assert plans["avalanche"]["order"] == [car, family]
    assert Decimal(plans["avalanche"]["interest"]) < Decimal(plans["snowball"]["interest"])
    assert Decimal(plans["saved"]) == Decimal(plans["snowball"]["interest"]) - Decimal(
        plans["avalanche"]["interest"]
    )
    assert plans["minimums"]["months"] > plans["avalanche"]["months"]

    # Forgetting what was typed, and a setting that can't be read, are both "nothing typed".
    assert put(family) == 204
    row = db.get(AppSetting, savings.TERMS_KEY + car)
    assert row is not None
    row.setting_value = "not json"
    db.commit()
    lines = {d.key: d for d in savings.debts(db, DAY)}
    assert not lines[family].planned and not lines[car].planned
    assert savings.payoff_plans(list(lines.values()), Decimal(0)) is None


def _item(**kwargs: Any) -> networth.Item:
    base: dict[str, Any] = {
        "key": "holding-1",
        "name": "Loan",
        "side": "liability",
        "holding_class": "loan",
        "value": Decimal(12000),
        "as_of": DAY,
        "source": "manual",
    }
    return networth.Item(**{**base, **kwargs})


def test_a_loans_terms_come_from_its_table_or_its_payment() -> None:
    # 24 installments left on 12,000 with 1,200 of interest still to pay: 1,200 over an average
    # balance of 6,000 for two years is 10% a year.
    table = loans.Schedule(
        installments=36,
        paid=12,
        left=24,
        next_period=date(2026, 11, 1),
        next_total=Decimal(550),
        payoff=date(2028, 10, 1),
        balance=Decimal(12000),
        interest_this_year=Decimal(0),
        interest_left=Decimal(1200),
        other_left=Decimal(0),
    )
    with_table = _item(loan=networth.Loan(Decimal(500), Decimal(0), 0, table))
    assert savings._loan_terms(with_table) == (Decimal("0.1000"), Decimal(550), "table")
    paying = _item(loan=networth.Loan(Decimal(500), Decimal(0), 0))
    assert savings._loan_terms(paying) == (None, Decimal(500), "payment")
    assert savings._loan_terms(_item()) == (None, None, None)


def test_a_card_shows_what_it_cost_but_is_not_planned_until_its_rate_is_typed(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = _item(
        key="account-7", name="Visa", holding_class="card", account_id=7, value=Decimal(2000)
    )
    cost = debt.AccountCost(7, "Visa", "credit_card", interest=Decimal(250), last_12=Decimal(310))
    monkeypatch.setattr(networth, "accounts", lambda *_: [card, _item(value=None)])
    monkeypatch.setattr(networth, "holdings", lambda *_: [])
    monkeypatch.setattr(debt, "cost", lambda *_: debt.DebtCost(2026, DAY, [], [cost], [2026]))
    [visa] = savings.debts(db, DAY)
    assert (visa.rate, visa.minimum, visa.planned, visa.interest_12) == (None, None, False, 310)
    assert savings.payoff_plans([visa], Decimal(0)) is None
