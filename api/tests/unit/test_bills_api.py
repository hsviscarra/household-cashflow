"""ADR-031: how often an item repeats, its due day, and the month's bills: paid, due or late."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, RecurringEntry, RecurringTemplate, Transaction
from app.services import recurring
from tests.unit.test_recurring_api import USER, _cat, _template

n = 0


def _gen(client: TestClient, month: str) -> None:
    assert (
        client.post("/api/recurring/generate", json={"month": month}, headers=USER).status_code
        == 200
    )


def _pay(db: Session, template_id: int, day: date, amount: str) -> None:
    global n
    n += 1
    entry = db.scalar(
        select(RecurringEntry).where(
            RecurringEntry.template_id == template_id, RecurringEntry.month == day.replace(day=1)
        )
    )
    assert entry is not None
    account = db.scalar(select(Account).where(Account.kind == "checking"))
    assert account is not None
    db.add(
        Transaction(
            natural_key=f"bill-{n}",
            account_id=account.account_id,
            txn_date=day,
            cash_month=day.replace(day=1),
            amount=Decimal(amount),
            description_raw=f"PAGO {n}",
            type="expense",
            source="statement",
            status="matched",
            recurring_entry_id=entry.entry_id,
        )
    )
    db.commit()


def _bills(client: TestClient, month: str = "2026-11-01") -> dict[str, dict[str, Any]]:
    out = client.get("/api/recurring/bills", params={"month": month, "today": "2026-11-06"})
    assert out.status_code == 200, out.text
    return {b["name"]: b for b in out.json()["bills"]}


def test_cadence_due_day_and_bills(client: TestClient, db: Session) -> None:
    cat = _cat(db, "Supermarket")
    biess = _template(
        client, name="BIESS", category_id=cat, amount="505.19", start_month="2026-08-01", due_day=7
    )
    _template(
        client,
        name="Insurance",
        category_id=cat,
        amount="1200",
        start_month="2026-11-01",
        every_months=12,
        due_day=1,
    )
    _template(
        client,
        name="Car tax",
        category_id=cat,
        amount="300",
        start_month="2026-11-01",
        every_months=0,
    )
    water = _template(
        client, name="Water", category_id=cat, amount="40", start_month="2026-09-01", every_months=2
    )
    house = _template(
        client,
        name="House",
        category_id=cat,
        amount="3075.36",
        start_month="2026-09-01",
        end_month="2028-02-01",
        every_months=1,
    )
    assert water["every_months"] == 2 and biess["due_day"] == 7
    # A new amount from October: shown as a price change.
    client.post(
        f"/api/recurring/templates/{biess['template_id']}/amount",
        json={"from_month": "2026-10-01", "amount": "510"},
        headers=USER,
    )
    for m in ("2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01", "2026-12-01"):
        _gen(client, m)

    # Only the months its cadence falls on get an entry.
    def months_of(name: str) -> list[str]:
        t = db.scalar(select(RecurringTemplate).where(RecurringTemplate.name == name))
        assert t is not None
        return sorted(
            e.month.isoformat()
            for e in db.scalars(
                select(RecurringEntry).where(RecurringEntry.template_id == t.template_id)
            )
        )

    assert months_of("Water") == ["2026-09-01", "2026-11-01"]
    assert months_of("Insurance") == ["2026-11-01"] and months_of("Car tax") == ["2026-11-01"]

    _pay(db, biess["template_id"], date(2026, 9, 7), "-505.19")
    _pay(db, biess["template_id"], date(2026, 10, 7), "-510")
    _pay(db, biess["template_id"], date(2026, 11, 6), "-510")
    _pay(db, water["template_id"], date(2026, 9, 15), "-38")

    b = _bills(client)
    assert set(b) == {"BIESS", "Insurance", "Car tax", "Water", "House"}
    assert b["BIESS"]["status"] == "paid" and Decimal(b["BIESS"]["paid"]) == Decimal("-510")
    assert Decimal(b["BIESS"]["avg3"]) == Decimal("-507.595")
    assert Decimal(b["BIESS"]["price_from"]) == Decimal("-505.19")
    assert b["BIESS"]["price_changed"] == "2026-10-01"
    assert b["Insurance"]["status"] == "late" and b["Insurance"]["due_day"] == 1
    assert b["Water"]["due_day"] == 15 and b["Water"]["due_day_set"] is False
    assert b["Water"]["status"] == "due"
    assert b["Car tax"]["due_day"] is None and b["Car tax"]["status"] == "due"
    assert b["House"]["payments_left"] == 16
    assert (
        b["BIESS"]["group"] == "Groceries"
        and b["BIESS"]["category_path"] == "Groceries / Supermarket"
    )

    dec = _bills(client, "2026-12-01")
    assert "Water" not in dec and "Insurance" not in dec and "Car tax" not in dec
    assert dec["BIESS"]["status"] == "due"
    oct_ = _bills(client, "2026-10-01")
    assert oct_["House"]["status"] == "late"  # a past month without a line

    # Skipped stays skipped; editing cadence and day.
    entry = db.scalar(
        select(RecurringEntry).where(
            RecurringEntry.template_id == house["template_id"],
            RecurringEntry.month == date(2026, 11, 1),
        )
    )
    assert entry is not None
    entry.status = "skipped"
    db.commit()
    assert _bills(client)["House"]["status"] == "skipped"
    out = client.patch(
        f"/api/recurring/templates/{water['template_id']}",
        json={"every_months": 3, "due_day": 20},
        headers=USER,
    ).json()
    assert (out["every_months"], out["due_day"]) == (3, 20)
    kept = client.patch(
        f"/api/recurring/templates/{water['template_id']}",
        json={"every_months": None},
        headers=USER,
    ).json()
    assert kept["every_months"] == 3
    bad = {"every_months": 5}
    assert (
        client.patch(f"/api/recurring/templates/{water['template_id']}", json=bad).status_code
        == 422
    )
    assert client.get("/api/recurring/bills").status_code == 200


def test_due_in() -> None:
    t = RecurringTemplate(start_month=date(2026, 1, 1), every_months=3)
    assert [
        m.month
        for m in recurring.months(date(2026, 1, 1), date(2026, 12, 1))
        if recurring.due_in(t, m)
    ] == [
        1,
        4,
        7,
        10,
    ]
    assert recurring.due_in(
        RecurringTemplate(start_month=date(2026, 1, 1), every_months=None), date(2026, 5, 1)
    )  # type: ignore[arg-type]
