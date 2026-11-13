"""ADR-098: net worth ahead, from the balance sheet, the loans' tables and what was kept."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
TODAY = "2026-10-20"
D = Decimal


def _holding(client: TestClient, name: str, holding_class: str, value: str) -> int:
    resp = client.post(
        "/api/holdings",
        json={"name": name, "holding_class": holding_class, "value": value, "as_of": "2025-12-31"},
    )
    assert resp.status_code == 201, resp.text
    out: int = resp.json()["holding_id"]
    return out


def _line(db: Session, day: date, amount: str, category: str, type_: str) -> None:
    bank = db.scalar(select(Account).where(Account.name == "Produbanco Ahorros Hernan"))
    cat = db.scalar(select(Category).where(Category.name == category))
    assert bank is not None and cat is not None
    db.add(
        Transaction(
            natural_key=f"out-{day}-{amount}",
            account_id=bank.account_id,
            txn_date=day,
            cash_month=day.replace(day=1),
            amount=D(amount),
            description_raw="LINE",
            type=type_,
            category_id=cat.category_id,
            source="manual",
            status="confirmed",
        )
    )


def _ahead(client: TestClient, **params: Any) -> Any:
    return client.get("/api/networth/ahead", params={"today": TODAY, **params})


def test_nothing_loaded(client: TestClient) -> None:
    out = _ahead(client).json()
    assert D(out["net_today"]) == 0 and D(out["kept_a_year"]) == 0 and out["loans"] == []
    assert [y["year"] for y in out["years"]] == [2026, 2027, 2028, 2029, 2030, 2031]
    assert all(D(y["net"]) == 0 and y["milestones"] == [] for y in out["years"])


def test_years_ahead_from_the_balance_sheet(client: TestClient, db: Session) -> None:
    _holding(client, "Stock Market", "investment", "10000")
    _holding(client, "Home", "property", "100000")
    _holding(client, "Family loan", "personal_loan", "600")
    mortgage = _holding(client, "Mortgage", "loan", "12000")
    # The lender's table: 2,000 left in two installments (November and December 2026), with 30
    # of interest between them.
    up = client.post(
        f"/api/holdings/{mortgage}/schedule",
        files={"file": ("tabla.pdf", s.loan_table(), PDF)},
        headers=USER,
    )
    assert up.status_code == 200, up.text
    # September, the one whole month: 3,000 in and 1,000 spent. A year at that pace keeps 24,000.
    _line(db, date(2026, 9, 2), "3000", "Hernan", "income")
    _line(db, date(2026, 9, 9), "-1000", "Supermarket", "expense")
    db.commit()
    goal = client.post(
        "/api/goals",
        params={"today": TODAY},
        json={"name": "Trip", "target_amount": "5000", "target_date": "2028-06-30"},
    )
    assert goal.status_code == 201, goal.text

    out = _ahead(client).json()
    assert D(out["kept_a_year"]) == D(24000)
    assert D(out["net_today"]) == D(10000) + 100000 - 2000 - 600
    loans = {x["name"]: x for x in out["loans"]}
    assert loans["Mortgage"]["from_table"] and loans["Mortgage"]["paid_off"] == "2026-12-01"
    assert not loans["Family loan"]["from_table"]

    y0, y1, *_, y5 = out["years"]
    # The rest of 2026 is two whole months: 4,000 kept, less the table's 30 of interest. The
    # mortgage's 2,000 is paid from it; the family loan has no payment and stays.
    assert D(y0["kept"]) == D(3970) and D(y0["loans"]) == D(600)
    assert D(y0["cash"]) == D(1970)
    assert D(y0["investments"]) == D("10083.33")  # 5% a year for a sixth of one
    assert D(y0["net"]) == D(out["net_today"]) + 3970 + D("83.33")
    assert y0["milestones"] == ["Mortgage paid off"]
    assert D(y1["kept"]) == D(24000) and D(y1["cash"]) == D(25970)
    assert next(y for y in out["years"] if y["year"] == 2028)["milestones"] == ["Goal: Trip"]
    assert D(y5["net_low"]) < D(y5["net"]) < D(y5["net_high"])

    # The choices: ten years, half of what is free invested, the house growing 2% a year.
    ten = _ahead(client, years=10, invest_share="0.5", property_growth="0.02").json()
    assert len(ten["years"]) == 11 and D(ten["years"][1]["cash"]) < D(y1["cash"])
    assert D(ten["years"][1]["property"]) > D(100000)
    assert _ahead(client, years=7).status_code == 422
    assert _ahead(client, low="0.09", expected="0.05").status_code == 422
    assert _ahead(client, invest_share="2").status_code == 422
