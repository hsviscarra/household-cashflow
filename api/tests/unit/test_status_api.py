"""F12: each month complete, or what is missing."""

from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category
from app.services import status
from tests.fixtures import statements as s
from tests.fixtures.workbook import build

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
JUNE = "Del 01 Jun 2026 Al 30 Jun 2026"
JULY = "Del 01 Jul 2026 Al 31 Jul 2026"
PHONE = [("Jun 20", "4", "PAGO CONECEL", "-27.50")]  # a seeded rule categorizes it


def _status(client: TestClient, today: str) -> dict[str, Any]:
    out: dict[str, Any] = client.get("/api/status", params={"today": today}).json()
    return out


def _month(st: dict[str, Any], month: str) -> dict[str, Any]:
    out: dict[str, Any] = next(m for m in st["months"] if m["month"] == month)
    return out


def _texts(m: dict[str, Any]) -> list[str]:
    return [i["text"] for i in m["items"]]


def _upload(client: TestClient, name: str, data: bytes, approve: bool = True) -> dict[str, Any]:
    st = client.post("/api/statements", files=[("files", (name, data, PDF))], headers=USER)
    sid = st.json()[0]["statement"]["statement_file_id"]
    b: dict[str, Any] = client.post(f"/api/statements/{sid}/read").json()
    if approve:
        assert b["tieout_ok"], b["checks"]
        client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    return b


def _only_produbanco(db: Session) -> Account:
    """Switch off every account but Hernan's Produbanco savings (the fixture's account)."""
    keep = db.scalar(select(Account).where(Account.name == "Produbanco Ahorros Hernan"))
    assert keep is not None
    for a in db.scalars(select(Account)):
        a.is_active = a.account_id == keep.account_id
    db.commit()
    return keep


def test_nothing_loaded_shows_the_current_month_missing_every_statement(
    client: TestClient,
) -> None:
    st = _status(client, "2026-10-27")
    assert st["excel_through"] is None and st["loads"] == []
    [oct_] = st["months"]
    assert oct_["month"] == "2026-10-01" and oct_["complete"] is False
    assert "BofA Adv Plus Banking: no statement for October" in _texts(oct_)
    assert {i["kind"] for i in oct_["items"]} == {"statement"}
    assert {c["state"] for c in oct_["coverage"]} == {"none"}
    assert len(oct_["coverage"]) == len(st["accounts"])


def test_excel_months_are_complete_and_later_months_list_statements(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/history/excel/load",
        files={"file": ("Cash Flow.xlsx", build(), XLSX)},
        headers=USER,
    )
    assert resp.status_code == 200
    st = _status(client, "2026-03-15")
    assert st["excel_through"] == "2026-01-01"
    assert [m["month"] for m in st["months"][:3]] == ["2026-03-01", "2026-02-01", "2026-01-01"]
    jan = _month(st, "2026-01-01")
    assert (jan["source"], jan["complete"], jan["items"]) == ("excel", True, [])
    # March is checked up to today; a month with no statement at all says so.
    assert "Capital One Venture: no statement for March" in _texts(_month(st, "2026-03-01"))
    loads = st["loads"]
    assert loads[0]["source"] == "excel_history" and loads[0]["file_name"] == "Cash Flow.xlsx"
    assert loads[0]["loaded_by"] == "hernan@example.com"


def test_a_covered_month_with_everything_categorized_is_complete(
    client: TestClient, db: Session
) -> None:
    _only_produbanco(db)
    _upload(client, "june.pdf", s.produbanco_full(period=JUNE, opening="2000.00", lines=PHONE))
    june = _month(_status(client, "2026-07-10"), "2026-06-01")
    assert june["complete"] is True and june["items"] == []
    assert june["coverage"][0] == {
        "account_id": june["coverage"][0]["account_id"],
        "state": "full",
        "covered_days": 30,
        "days": 30,
    }
    # July: no statement yet, checked up to the 10th.
    july = _month(_status(client, "2026-07-10"), "2026-07-01")
    assert _texts(july) == ["Produbanco Ahorros Hernan: no statement for July"]
    loads = _status(client, "2026-07-10")["loads"]
    assert (loads[0]["source"], loads[0]["file_name"], loads[0]["rows"]) == (
        "statement",
        "june.pdf",
        1,
    )


def test_imports_lines_transfers_and_recurring_items_are_listed(
    client: TestClient, db: Session
) -> None:
    _only_produbanco(db)
    _upload(
        client,
        "june.pdf",
        s.produbanco_full(
            period=JUNE,
            opening="2000.00",
            lines=[
                *PHONE,
                ("Jun 21", "5", "DEBITO VISA", "-40.00"),  # no rule: needs a category
                ("Jun 22", "6", "PAGO TARJETA CREDITO PAGO DIRECTO B", "-100.00"),  # no card side
            ],
        ),
    )
    # July waits for approval; a second July statement doesn't tie out.
    july = s.produbanco_full(period=JULY, opening="1832.50", lines=PHONE)
    _upload(client, "july.pdf", july, approve=False)
    bad = s.produbanco_full(period=JULY, opening="1832.50", lines=PHONE * 4, balance_delta="5")
    assert _upload(client, "july-bad.pdf", bad, approve=False)["tieout_ok"] is False
    # A recurring item expected in June with no line paying it.
    water = db.scalar(select(Category).where(Category.name == "Water"))
    assert water is not None
    client.post(
        "/api/recurring/templates",
        json={
            "name": "Water",
            "category_id": water.category_id,
            "type": "expense",
            "amount": "40",
            "start_month": "2026-06-01",
        },
    )
    client.post("/api/recurring/generate", json={"month": "2026-06-01"})

    st = _status(client, "2026-07-31")
    june = _month(st, "2026-06-01")
    kinds = {i["kind"]: i for i in june["items"]}
    assert set(kinds) == {"uncategorized", "transfer", "recurring"}
    assert kinds["uncategorized"]["text"] == "1 line needs a category"
    assert kinds["uncategorized"]["link"] == "/review?month=2026-06"
    assert kinds["transfer"]["text"] == "1 transfer is missing the other side"
    assert kinds["recurring"]["text"] == "1 recurring item not paid yet: Water"
    assert kinds["recurring"]["link"] == "/recurring?year=2026"
    july_items = _month(st, "2026-07-01")["items"]
    imports = [i["text"] for i in july_items if i["kind"] == "import"]
    assert imports == ["july.pdf waits for approval", "july-bad.pdf doesn't tie out"]
    assert all(
        i["link"].startswith("/import/batches/") for i in july_items if i["kind"] == "import"
    )


def test_partial_coverage_and_balance_breaks(client: TestClient, db: Session) -> None:
    _only_produbanco(db)
    # July is approved first, then a June statement that closes at a different balance: the
    # chain breaks where July starts. (Approved in order, the tie-out would have refused July.)
    _upload(client, "july.pdf", s.produbanco_full(period=JULY, opening="2000.00", lines=PHONE))
    _upload(
        client,
        "june.pdf",
        s.produbanco_full(period="Del 10 Jun 2026 Al 30 Jun 2026", opening="1500.00", lines=PHONE),
    )
    st = _status(client, "2026-08-02")
    july = _month(st, "2026-07-01")
    assert _texts(july) == [
        "Produbanco Ahorros Hernan: opens at 2,000.00 on Jul 1 but the previous statement "
        "closed at 1,472.50"
    ]
    assert july["items"][0]["kind"] == "balance"
    june = _month(st, "2026-06-01")
    assert _texts(june) == ["Produbanco Ahorros Hernan: no statement for Jun 1\u20139"]
    assert june["coverage"][0]["state"] == "partial" and june["coverage"][0]["covered_days"] == 21
    assert _texts(_month(st, "2026-08-01")) == [
        "Produbanco Ahorros Hernan: no statement for August"
    ]


def test_gaps_and_day_ranges() -> None:
    d = date
    assert status._gaps([], d(2026, 6, 1), d(2026, 6, 30)) == [(d(2026, 6, 1), d(2026, 6, 30))]
    periods = [
        (d(2026, 5, 20), d(2026, 6, 3)),
        (d(2026, 6, 10), d(2026, 6, 15)),
        (d(2026, 6, 12), d(2026, 7, 5)),
    ]
    assert status._gaps(periods, d(2026, 6, 1), d(2026, 6, 30)) == [(d(2026, 6, 4), d(2026, 6, 9))]
    assert status._gaps([(d(2026, 8, 1), d(2026, 8, 31))], d(2026, 6, 1), d(2026, 6, 30)) == [
        (d(2026, 6, 1), d(2026, 6, 30))
    ]
    assert status._days(d(2026, 6, 5), d(2026, 6, 5)) == "Jun 5"
    assert status._days(d(2026, 9, 28), d(2026, 10, 3)) == "Sep 28\u2013Oct 3"
    assert status.month_end(d(2026, 2, 1)) == d(2026, 2, 28)
