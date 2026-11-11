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
    # July: no statement yet, checked up to the 10th; the bank issues it at the month's end.
    july = _month(_status(client, "2026-07-10"), "2026-07-01")
    assert _texts(july) == [
        "Produbanco Ahorros Hernan: no statement for July (the bank issues it around Jul 31)"
    ]
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
    assert _texts(june) == [
        "Produbanco Ahorros Hernan: no statement for Jun 1\u20139"
        " \u00b7 download the statement closing Jun 9"
    ]
    assert june["coverage"][0]["state"] == "partial" and june["coverage"][0]["covered_days"] == 21
    assert _texts(_month(st, "2026-08-01")) == [
        "Produbanco Ahorros Hernan: no statement for August (the bank issues it around Aug 31)"
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


def test_a_closed_account_is_expected_only_until_it_closed(client: TestClient, db: Session) -> None:
    keep = _only_produbanco(db)
    _upload(client, "jun.pdf", s.produbanco_full(period=JUNE, lines=PHONE))
    # Suspended on July 10: July is expected up to the 10th only, August not at all.
    resp = client.patch(f"/api/accounts/{keep.account_id}", json={"closed_on": "2026-07-10"})
    assert resp.json()["closed_on"] == "2026-07-10"
    st = _status(client, "2026-08-20")
    jul = _month(st, "2026-07-01")
    assert _texts(jul) == [
        "Produbanco Ahorros Hernan: no statement for July (until it closed on Jul 10)"
        " \u00b7 download the statement closing Jul 31"
    ]
    assert jul["coverage"][0]["days"] == 10
    aug = _month(st, "2026-08-01")
    assert not [t for t in _texts(aug) if "Produbanco" in t] and aug["coverage"] == []
    # Its earlier statements still load, and reopening it expects August again.
    client.patch(f"/api/accounts/{keep.account_id}", json={"closed_on": None})
    aug = _month(_status(client, "2026-08-20"), "2026-08-01")
    assert "Produbanco Ahorros Hernan: no statement for August" in _texts(aug)


def test_a_missing_statement_already_on_import_says_where_it_stands(
    client: TestClient, db: Session
) -> None:
    _only_produbanco(db)
    # Only approved statements count; one on the Import page says where it stands.
    up = client.post(
        "/api/statements",
        files=[("files", ("jul.pdf", s.produbanco_full(period=JULY), PDF))],
        headers=USER,
    ).json()[0]["statement"]
    jul = _month(_status(client, "2026-07-31"), "2026-07-01")
    assert _texts(jul) == [
        "Produbanco Ahorros Hernan: no statement for July: on Import, uploaded, not read yet"
    ]
    client.post(f"/api/statements/{up['statement_file_id']}/read")
    jul = _month(_status(client, "2026-07-31"), "2026-07-01")
    assert _texts(jul)[0] == (
        "Produbanco Ahorros Hernan: no statement for July: on Import, waiting for approval"
    )


def test_statements_by_account_show_each_period_and_the_gaps(
    client: TestClient, db: Session
) -> None:
    _only_produbanco(db)
    _upload(client, "jun.pdf", s.produbanco_full(period=JUNE, lines=PHONE))  # loaded
    aug = "Del 01 Ago 2026 Al 31 Ago 2026"
    _upload(client, "aug.pdf", s.produbanco_full(period=aug, opening="900.00"), approve=False)
    [acc] = _status(client, "2026-09-10")["statements"]
    assert acc["name"] == "Produbanco Ahorros Hernan" and acc["start_day"] == 1
    assert [(x["file_name"], x["start"], x["end"], x["state"]) for x in acc["statements"]] == [
        ("jun.pdf", "2026-06-01", "2026-06-30", "loaded"),
        ("aug.pdf", "2026-08-01", "2026-08-31", "waiting"),
    ]
    # July is missing; September is the current cycle, issued around Sep 30.
    assert acc["gaps"] == [
        # Filled by the statement closing Jul 31 (Produbanco names don't carry the date).
        {
            "start": "2026-07-01",
            "end": "2026-07-31",
            "due": None,
            "closes": ["2026-07-31"],
            "files": [],
        },
        {
            "start": "2026-09-01",
            "end": "2026-09-10",
            "due": "2026-09-30",
            "closes": [],
            "files": [],
        },
    ]


def test_next_cycle_end() -> None:
    assert status.next_cycle_end(date(2026, 1, 22)) == date(2026, 2, 22)
    assert status.next_cycle_end(date(2026, 1, 31)) == date(2026, 2, 28)  # month end stays one
    assert status.next_cycle_end(date(2026, 6, 30)) == date(2026, 7, 31)
    assert status.next_cycle_end(date(2026, 12, 3)) == date(2027, 1, 3)


def test_which_statements_fill_a_gap() -> None:
    # A month missing between two Capital One statements: the one closing Jul 3.
    assert status.statement_closes(
        date(2026, 6, 4), date(2026, 7, 3), date(2026, 6, 3), date(2026, 7, 4), date(2026, 11, 4)
    ) == [date(2026, 7, 3)]
    # Two months missing before a statement: both, oldest first.
    assert status.statement_closes(
        date(2026, 5, 4), date(2026, 7, 3), None, date(2026, 7, 4), date(2026, 11, 4)
    ) == [date(2026, 6, 3), date(2026, 7, 3)]
    # After the last statement: only those already issued (Nov 3 yes, Dec 3 not yet).
    assert status.statement_closes(
        date(2026, 10, 4), date(2026, 11, 4), date(2026, 10, 3), None, date(2026, 11, 4)
    ) == [date(2026, 11, 3)]
    assert (
        status.statement_closes(date(2026, 1, 1), date(2026, 1, 31), None, None, date(2026, 2, 5))
        == []
    )
    assert status.prev_cycle_end(date(2026, 3, 31)) == date(2026, 2, 28)
    assert status.prev_cycle_end(date(2026, 1, 22)) == date(2025, 12, 22)


def test_file_names_by_bank() -> None:
    from types import SimpleNamespace

    nov3 = [date(2026, 11, 3)]
    co = SimpleNamespace(institution="Capital One", last4="4003")
    assert status._file_names(co, nov3) == ["Statement_112026_4003.pdf"]  # type: ignore[arg-type]
    bofa = SimpleNamespace(institution="Bank of America", last4="8872")
    assert status._file_names(bofa, [date(2026, 11, 22)]) == ["eStmt_2026-11-22.pdf"]  # type: ignore[arg-type]
    pc = SimpleNamespace(institution="Pacificard", last4=None)
    assert status._file_names(pc, [date(2026, 10, 23)]) == ["ESTADOCUENTA202610.pdf"]  # type: ignore[arg-type]
    other = SimpleNamespace(institution="Diners Club", last4=None)
    assert status._file_names(other, nov3) == []  # type: ignore[arg-type]


def test_the_same_period_twice_is_not_a_break() -> None:
    """Two files of one statement (or overlapping ranges) compare with the statement that ends
    before them, not with each other (three false breaks on 2026-11-10)."""
    from decimal import Decimal

    from app.models import Account
    from app.services import status

    def stmt(fid: int, start: date, end: date, opening: str, closing: str) -> status._Stmt:
        return status._Stmt(fid, f"{fid}.pdf", 1, start, end, Decimal(opening), Decimal(closing))

    stmts = [
        stmt(1, date(2026, 7, 23), date(2026, 8, 22), "5000.00", "5968.07"),
        stmt(2, date(2026, 8, 23), date(2026, 9, 22), "5968.07", "6856.04"),
        stmt(3, date(2026, 9, 23), date(2026, 10, 22), "6856.04", "7453.01"),
        stmt(4, date(2026, 9, 23), date(2026, 10, 22), "6856.04", "7453.01"),  # same, again
        stmt(5, date(2026, 10, 23), date(2026, 11, 22), "7000.00", "7100.00"),  # a real break
    ]
    months = [status.MonthStatus(date(2026, m, 1), "statements") for m in (8, 9, 10)]
    acct = Account(account_id=1, name="BofA")
    status._balance_breaks(None, {1: stmts}, {1: acct}, months)  # type: ignore[arg-type]
    texts = [i.text for ms in months for i in ms.items]
    assert texts == [
        "BofA: opens at 7,000.00 on Oct 23 but the previous statement closed at 7,453.01"
    ]


def test_a_period_only_the_parser_read_still_counts(client: TestClient, db: Session) -> None:
    """A statement whose period upload couldn't read (a garbled first page) uses the period the
    parser read, so Data Status doesn't ask for it again."""
    from app.models import StatementFile

    _only_produbanco(db)
    _upload(client, "jun.pdf", s.produbanco_full(period=JUNE, lines=PHONE))
    sf = db.scalar(select(StatementFile).where(StatementFile.file_name == "jun.pdf"))
    assert sf is not None and sf.period_start == date(2026, 6, 1)
    sf.period_start = sf.period_end = None  # as an old upload left it
    db.commit()
    [acc] = _status(client, "2026-07-10")["statements"]
    assert [(x["start"], x["end"]) for x in acc["statements"]] == [("2026-06-01", "2026-06-30")]
    assert [g["start"] for g in acc["gaps"]] == ["2026-07-01"]
    assert "the bank issues it around Jul 31" in " ".join(
        _texts(_month(_status(client, "2026-07-10"), "2026-07-01"))
    )


def test_an_account_is_not_expected_before_it_opened(client: TestClient, db: Session) -> None:
    """ADR-071: an account opened in August isn't missing July."""
    keep = _only_produbanco(db)
    _upload(client, "jun.pdf", s.produbanco_full(period=JUNE, lines=PHONE))
    st = _status(client, "2026-08-20")
    assert any("Produbanco" in t for t in _texts(_month(st, "2026-07-01")))
    resp = client.patch(f"/api/accounts/{keep.account_id}", json={"opened_on": "2026-08-01"})
    assert resp.json()["opened_on"] == "2026-08-01"
    st = _status(client, "2026-08-20")
    jul = _month(st, "2026-07-01")
    assert not [t for t in _texts(jul) if "Produbanco" in t] and jul["coverage"] == []
    [acc] = st["statements"]
    assert acc["opened_on"] == "2026-08-01"
    assert all(g["start"] >= "2026-08-01" for g in acc["gaps"])
