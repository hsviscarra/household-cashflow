"""F14 (ADR-014): a lender's amortization table fills the loan's installments, its balance on the
balance sheet, the payment check against bank lines and the projected installments."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, BalanceSnapshot, Category, LoadLog, RecurringEntry, Transaction
from app.services import loans
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _cat(db: Session, name: str) -> int:
    c = db.scalar(select(Category).where(Category.name == name))
    assert c is not None, name
    return c.category_id


def _loan(client: TestClient, **extra: Any) -> int:
    body = {"name": "Mortgage", "holding_class": "loan", "value": "12000", "as_of": "2025-12-31"}
    resp = client.post("/api/holdings", json={**body, **extra})
    assert resp.status_code == 201, resp.text
    out: int = resp.json()["holding_id"]
    return out


def _upload(client: TestClient, holding_id: int, data: bytes) -> Any:
    return client.post(
        f"/api/holdings/{holding_id}/schedule",
        files={"file": ("tabla.pdf", data, PDF)},
        headers=USER,
    )


def _item(client: TestClient, name: str, as_of: str = "2026-10-27") -> dict[str, Any]:
    items = client.get("/api/networth", params={"as_of": as_of}).json()["items"]
    out: dict[str, Any] = next(i for i in items if i["name"] == name)
    return out


def test_read_table() -> None:
    t = loans.read_table(s.loan_table())
    assert (len(t.rows), t.term, t.approved, t.problems) == (12, 12, Decimal("12000.00"), [])
    third = t.rows[2]
    assert (third.principal, third.interest, third.other, third.total) == (
        Decimal("1000.00"),
        Decimal("100.00"),
        Decimal("6.50"),
        Decimal("1106.50"),
    )
    assert t.rows[9].paid and not t.rows[10].paid and t.rows[-1].balance_after == 0


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        (s.loan_table(skip=5), "Installment 5 is missing"),
        (s.loan_table(bad_total=4), "Installment 4: its amounts don't add up"),
        (s.loan_table(heading="12500.00"), "Installment 1: the balance"),
    ],
)
def test_checks(data: bytes, problem: str) -> None:
    assert any(problem in p for p in loans.read_table(data).problems)


def test_not_a_table() -> None:
    with pytest.raises(loans.LoanError, match="isn't an amortization table"):
        loans.read_table(s.bofa())
    with pytest.raises(loans.LoanError, match="could not be read"):
        loans.read_table(b"not a pdf")
    with pytest.raises(loans.LoanError, match="No installments"):
        loans.read_table(s.pdf(["TABLA DE AMORTIZACION", "nothing else"]))


def test_upload_fills_the_balance_and_summary(client: TestClient, db: Session) -> None:
    hid = _loan(client)
    out = _upload(client, hid, s.loan_table())
    assert out.status_code == 200, out.text
    assert out.json() == {
        "installments": 12,
        "paid": 10,
        "due": 2,
        "balance": "2000.00",
        "as_of": "2026-10-01",
    }
    item = _item(client, "Mortgage")
    assert Decimal(item["value"]) == 2000 and item["source"] == "amortization"
    sched = item["loan"]["schedule"]
    assert (sched["paid"], sched["left"], sched["payoff"]) == (10, 2, "2026-12-01")
    assert (sched["next_period"], Decimal(sched["next_total"])) == ("2026-11-01", Decimal("1022.5"))
    assert Decimal(item["loan"]["monthly_payment"]) == Decimal("1022.5")
    assert Decimal(sched["interest_this_year"]) == 750
    assert (Decimal(sched["interest_left"]), Decimal(sched["other_left"])) == (30, 5)
    # The balance in June came from the table too; the manual opening value stays.
    assert Decimal(_item(client, "Mortgage", "2026-06-30")["value"]) == 6000
    assert Decimal(_item(client, "Mortgage", "2025-12-31")["value"]) == 12000
    log = db.scalar(select(LoadLog).where(LoadLog.source == "amortization"))
    assert log is not None and log.rows_loaded == 12 and "tabla" not in (log.summary or "")

    # A newer table replaces the installments and the table's balances.
    assert _upload(client, hid, s.loan_table(paid=11)).status_code == 200
    snaps = db.scalars(
        select(BalanceSnapshot).where(
            BalanceSnapshot.holding_id == hid, BalanceSnapshot.source == "amortization"
        )
    ).all()
    assert len(snaps) == 11
    assert Decimal(_item(client, "Mortgage", "2026-11-30")["value"]) == 1000
    assert len(loans.installments(db, hid)) == 12


def test_upload_refusals(client: TestClient) -> None:
    hid = _loan(client)
    bad = _upload(client, hid, s.loan_table(skip=3))
    assert bad.status_code == 422 and "Installment 3 is missing" in bad.json()["detail"]
    assert _item(client, "Mortgage")["loan"]["schedule"] is None
    car = client.post(
        "/api/holdings",
        json={"name": "Car", "holding_class": "vehicle", "value": "100", "as_of": "2026-01-01"},
    ).json()["holding_id"]
    assert "isn't a loan" in _upload(client, car, s.loan_table()).json()["detail"]
    assert _upload(client, 9999, s.loan_table()).status_code == 404
    big = b"%PDF" + b"0" * (10 * 1024 * 1024 + 1)
    assert _upload(client, hid, big).status_code == 413


def _line(db: Session, n: int, day: date, amount: str, text: str, cat: int | None) -> Transaction:
    acct = db.scalar(select(Account).where(Account.name == "Produbanco Ahorros Hernan"))
    assert acct is not None
    t = Transaction(
        natural_key=f"loan-{n}",
        account_id=acct.account_id,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=Decimal(amount),
        description_raw=text,
        type="debt_payment",
        category_id=cat,
        source="manual",
        status="confirmed",
    )
    db.add(t)
    return t


def test_payment_check_and_projection(client: TestClient, db: Session) -> None:
    mortgage = _cat(db, "Mortgage BIESS")
    template = client.post(
        "/api/recurring/templates",
        json={
            "name": "Mortgage",
            "category_id": mortgage,
            "type": "expense",
            "amount": "1100",
            "start_month": "2026-01-01",
        },
    ).json()["template_id"]
    hid = _loan(client, recurring_template_id=template)
    assert _upload(client, hid, s.loan_table()).status_code == 200

    # August paid by a transfer naming the lender, September in the loan's category, October
    # through the recurring item's entry; a 1.00+ difference or an unrelated line doesn't count.
    _line(db, 1, date(2026, 8, 6), "-1052.50", "TRANSFERENCIA PAGO IESS", None)
    _line(db, 2, date(2026, 9, 5), "-1042.00", "TRANSFER OUT", mortgage)
    oct_line = _line(db, 3, date(2026, 10, 7), "-1032.50", "PAYMENT", None)
    _line(db, 4, date(2026, 7, 6), "-1050.00", "TRANSFERENCIA PAGO IESS", None)
    _line(db, 5, date(2026, 6, 6), "-1072.50", "SUPERMARKET", None)
    client.post("/api/recurring/generate", json={"month": "2026-10-01"})
    entry = db.scalar(
        select(RecurringEntry).where(
            RecurringEntry.template_id == template, RecurringEntry.month == date(2026, 10, 1)
        )
    )
    assert entry is not None
    db.flush()
    oct_line.recurring_entry_id = entry.entry_id
    db.commit()

    got = client.get(f"/api/holdings/{hid}/payments", params={"today": "2026-10-27"}).json()
    by = {p["period"][:7]: p for p in got}
    assert list(by) == [f"2026-{m:02d}" for m in range(1, 13)]  # 10 paid this year, 2 due
    assert by["2026-08"]["line_description"] == "TRANSFERENCIA PAGO IESS"
    assert by["2026-08"]["account_name"] == "Produbanco Ahorros Hernan"
    assert by["2026-09"]["line_date"] == "2026-09-05"
    assert by["2026-10"]["line_id"] == oct_line.transaction_id
    assert by["2026-07"]["line_id"] is None  # 1050 vs 1062.50: more than 1.00 off
    assert by["2026-06"]["line_id"] is None  # not a loan payment
    assert by["2026-11"]["status"] == "due" and by["2026-11"]["line_id"] is None

    # Projection: November and December pay the table's installment; January nothing.
    proj = client.get("/api/projections", params={"today": "2026-10-27"}).json()
    fixed = {m["month"]: [e for e in m["items"] if e["name"] == "Mortgage"] for m in proj["months"]}
    assert Decimal(fixed["2026-11-01"][0]["amount"]) == Decimal("-1022.5")
    assert Decimal(fixed["2026-12-01"][0]["amount"]) == Decimal("-1012.5")
    assert fixed["2027-01-01"] == []


def test_payments_without_a_recurring_item(client: TestClient, db: Session) -> None:
    hid = _loan(client)
    assert client.get(f"/api/holdings/{hid}/payments").json() == []
    _upload(client, hid, s.loan_table())
    sched = loans.schedule(db, hid, date(2026, 10, 27))
    assert sched is not None and sched.next_total == Decimal("1022.50")
    assert Decimal(_item(client, "Mortgage")["loan"]["monthly_payment"]) == Decimal("1022.5")
