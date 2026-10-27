"""F11: recurring templates, month entries, matching and the month grid."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, ChangeLog, RecurringEntry, Transaction
from app.services import recurring
from tests.fixtures import statements as s
from tests.fixtures.workbook import build

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
JUNE = "2026-06-01"


def _cat(db: Session, name: str) -> int:
    c = db.scalar(select(Category).where(Category.name == name))
    assert c is not None, name
    return c.category_id


def _excel(client: TestClient, data: bytes | None = None) -> None:
    resp = client.post(
        "/api/history/excel/load",
        files={"file": ("Cash Flow.xlsx", data or build(), XLSX)},
        headers=USER,
    )
    assert resp.status_code == 200, resp.text


def _statement(client: TestClient, lines: list[tuple[str, str, str, str]]) -> None:
    data = s.produbanco_full(
        period="Del 01 Jun 2026 Al 30 Jun 2026", opening="5000.00", lines=lines
    )
    st = client.post("/api/statements", files=[("files", ("p.pdf", data, PDF))], headers=USER)
    sid = st.json()[0]["statement"]["statement_file_id"]
    b = client.post(f"/api/statements/{sid}/read").json()
    assert b["tieout_ok"], b["checks"]
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)


def _template(client: TestClient, **body: Any) -> dict[str, Any]:
    payload = {"type": "expense", "start_month": "2026-06-01", **body}
    resp = client.post("/api/recurring/templates", json=payload, headers=USER)
    assert resp.status_code == 201, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _grid(client: TestClient, year: int = 2026) -> dict[str, dict[str, Any]]:
    g = client.get("/api/recurring/grid", params={"year": year}).json()
    return {r["name"]: r for r in g["rows"]}


def _cell(row: dict[str, Any], month: int) -> dict[str, Any]:
    out: dict[str, Any] = row["cells"][month - 1]
    return out


# ---------------------------------------------------------------- from the workbook
def test_excel_rows_become_templates_and_reproduce_the_sheet(client: TestClient) -> None:
    assert client.get("/api/recurring/excel-rows", params={"year": 2026}).json() == []
    _excel(client)
    rows = {r["name"]: r for r in client.get("/api/recurring/excel-rows?year=2026").json()}
    # Rows with a planned value (July) are suggested; one-month rows are listed but not ticked.
    assert rows["Hernan (Salaries)"]["suggested"] and rows["Interactive Brokers"]["suggested"]
    assert not rows["Office Rent"]["suggested"] and rows["Office Rent"]["months"] == 1
    assert rows["Hernan (Health Appointments)"]["category_path"] == "Health / Doctors"
    assert Decimal(rows["Lauren"]["latest"]) == Decimal("3200")

    names = ["Lauren", "Hernan (Salaries)", "Interactive Brokers", "Office Rent"]
    made = client.post(
        "/api/recurring/from-excel", json={"year": 2026, "names": names}, headers=USER
    ).json()
    assert made == {"templates": 4, "entries": 7, "linked": 4}

    grid = _grid(client)
    assert list(grid) == [*names[:2], "Office Rent", "Interactive Brokers"]  # sheet order
    lauren = grid["Lauren"]
    assert lauren["group"] == "Salaries" and lauren["type"] == "income"
    jan, jul = _cell(lauren, 1), _cell(lauren, 7)
    assert (jan["status"], Decimal(jan["actual"]), jan["lines"]) == ("matched", Decimal("3100"), 1)
    assert jan["is_override"]  # January's 3,100 differs from the template's 3,200
    assert (jul["status"], Decimal(jul["expected"])) == ("planned", Decimal("3200"))
    assert _cell(lauren, 3)["status"] == "not_generated"
    ib = grid["Interactive Brokers"]
    assert Decimal(_cell(ib, 1)["actual"]) == Decimal("-700")
    assert _cell(grid["Office Rent"], 1)["status"] == "matched"

    # Asking again creates nothing new; the rows say they already exist.
    again = client.post("/api/recurring/from-excel", json={"year": 2026, "names": names}).json()
    assert again["templates"] == 0
    assert client.get("/api/recurring/excel-rows?year=2026").json()[0]["exists"] is True
    bad = client.post("/api/recurring/from-excel", json={"year": 2026, "names": ["Nope"]})
    assert bad.status_code == 422

    # The Overview's plan for July now comes from the entries.
    plan = {p["month"]: p for p in client.get("/api/cashflow/plan").json()}
    assert Decimal(plan["2026-07-01"]["income"]) == Decimal("3200") + Decimal("4900")
    assert Decimal(plan["2026-07-01"]["outflows"]) == Decimal("700")

    # A reloaded workbook replaces the history lines; they are linked again.
    _excel(client, build(lauren_jan_2026=3150))
    assert Decimal(_cell(_grid(client)["Lauren"], 1)["actual"]) == Decimal("3150")


# ---------------------------------------------------------------- templates and months
def test_template_change_generate_copy_and_edit(client: TestClient, db: Session) -> None:
    condo = _template(
        client,
        name="Condo",
        category_id=_cat(db, "Condo Fee"),
        amount="269",
        start_month="2026-06-15",
    )
    assert condo["start_month"] == "2026-06-01" and Decimal(condo["amount"]) == Decimal("269")
    assert condo["group"] == "Housing"
    tid = condo["template_id"]

    assert client.post("/api/recurring/generate", json={"month": "2026-06-01"}).json() == {
        "count": 1
    }
    assert client.post("/api/recurring/generate", json={"month": "2026-06-01"}).json() == {
        "count": 0
    }
    assert client.post("/api/recurring/generate", json={"month": "2026-05-01"}).json() == {
        "count": 0
    }
    # Copy June to July-September, then change the amount from August on.
    copied = client.post(
        "/api/recurring/copy",
        json={"from_month": JUNE, "to_start": "2026-07-01", "to_end": "2026-09-01"},
    )
    assert copied.json() == {"count": 3}
    jul_id = _cell(_grid(client)["Condo"], 7)["entry_id"]
    edited = client.patch(f"/api/recurring/entries/{jul_id}", json={"amount": "300"}, headers=USER)
    assert edited.json()["is_override"] and Decimal(edited.json()["amount"]) == Decimal("-300")
    changed = client.post(
        f"/api/recurring/templates/{tid}/amount", json={"from_month": "2026-08-01", "amount": "280"}
    )
    assert changed.json() == {"count": 2}
    row = _grid(client)["Condo"]
    assert [Decimal(_cell(row, m)["expected"]) for m in (6, 7, 8, 9)] == [
        Decimal("-269"),
        Decimal("-300"),  # set by hand: the change leaves it alone
        Decimal("-280"),
        Decimal("-280"),
    ]
    assert _cell(row, 10)["status"] == "not_generated" and _cell(row, 5)["status"] == "none"
    t = client.get("/api/recurring/templates").json()[0]
    assert [(a["from_month"], Decimal(a["amount"])) for a in t["amounts"]] == [
        ("2026-06-01", Decimal("269")),
        ("2026-08-01", Decimal("280")),
    ]

    # Reset July to the template, skip September, then plan it again.
    reset = client.patch(f"/api/recurring/entries/{jul_id}", json={"reset": True}).json()
    assert (Decimal(reset["amount"]), reset["is_override"]) == (Decimal("-269"), False)
    sep_id = _cell(row, 9)["entry_id"]
    skipped = client.patch(
        f"/api/recurring/entries/{sep_id}", json={"status": "skipped", "notes": "Paid in Oct"}
    )
    assert skipped.json()["status"] == "skipped" and skipped.json()["notes"] == "Paid in Oct"
    plan = {p["month"]: p for p in client.get("/api/cashflow/plan").json()}
    assert "2026-09-01" not in plan and Decimal(plan["2026-08-01"]["outflows"]) == Decimal("280")
    client.patch(f"/api/recurring/entries/{sep_id}", json={"status": "planned"})

    # Copying a skipped month copies the skip; matched entries keep their amount.
    client.patch(f"/api/recurring/entries/{sep_id}", json={"status": "skipped"})
    client.post(
        "/api/recurring/copy",
        json={
            "from_month": "2026-09-01",
            "to_start": "2026-10-01",
            "to_end": "2026-10-01",
            "template_ids": [tid],
        },
    )
    assert _cell(_grid(client)["Condo"], 10)["status"] == "skipped"

    # Edit and end the template; changes are logged.
    patched = client.patch(
        f"/api/recurring/templates/{tid}",
        json={
            "name": "Condo fee",
            "end_month": "2026-10-20",
            "match_pattern": "  CONDO ",
            "notes": "x",
        },
        headers=USER,
    )
    assert patched.status_code == 200
    assert (patched.json()["end_month"], patched.json()["match_pattern"]) == ("2026-10-01", "CONDO")
    assert _cell(_grid(client)["Condo fee"], 11)["status"] == "none"
    assert db.scalar(
        select(ChangeLog).where(
            ChangeLog.table_name == "core.recurring_template", ChangeLog.column_name == "end_month"
        )
    )
    # Remove one month's entry, then the template.
    assert client.delete(f"/api/recurring/entries/{sep_id}").status_code == 204
    assert client.delete(f"/api/recurring/entries/{sep_id}").status_code == 404
    assert client.delete(f"/api/recurring/templates/{tid}").status_code == 204
    assert client.get("/api/recurring/templates").json() == []
    assert db.scalars(select(RecurringEntry)).all() == []


def test_type_change_flips_signs_and_validation(client: TestClient, db: Session) -> None:
    rent = _template(
        client, name="Office", category_id=_cat(db, "Office Rent"), amount="575", type="income"
    )
    client.post("/api/recurring/generate", json={"month": JUNE})
    assert Decimal(_cell(_grid(client)["Office"], 6)["expected"]) == Decimal("575")
    tid = rent["template_id"]
    client.patch(f"/api/recurring/templates/{tid}", json={"type": "expense"})
    assert Decimal(_cell(_grid(client)["Office"], 6)["expected"]) == Decimal("-575")

    cat = _cat(db, "Condo Fee")
    dup = client.post(
        "/api/recurring/templates",
        json={
            "name": "Office",
            "category_id": cat,
            "type": "expense",
            "amount": "1",
            "start_month": JUNE,
        },
    )
    assert dup.status_code == 409
    for body, code in [
        ({"name": " ", "category_id": cat, "amount": "1"}, 422),
        ({"name": "X", "category_id": 99999, "amount": "1"}, 422),
        ({"name": "X", "category_id": cat, "amount": "1", "end_month": "2026-01-01"}, 422),
        ({"name": "X", "category_id": cat, "amount": "-1"}, 422),
    ]:
        resp = client.post(
            "/api/recurring/templates", json={"type": "expense", "start_month": JUNE, **body}
        )
        assert resp.status_code == code, body
    assert client.patch(f"/api/recurring/templates/{tid}", json={"name": " "}).status_code == 422
    _template(client, name="Other", category_id=cat, amount="5")
    assert (
        client.patch(f"/api/recurring/templates/{tid}", json={"name": "Other"}).status_code == 409
    )
    early = client.patch(f"/api/recurring/templates/{tid}", json={"end_month": "2026-01-01"})
    assert early.status_code == 422
    assert client.patch("/api/recurring/templates/9999", json={"notes": "x"}).status_code == 404
    before = client.post(
        f"/api/recurring/templates/{tid}/amount", json={"from_month": "2026-01-01", "amount": "1"}
    )
    assert before.status_code == 422
    for body in [
        {"from_month": JUNE, "to_start": "2026-08-01", "to_end": "2026-07-01"},
        {"from_month": JUNE, "to_start": "2026-05-01", "to_end": "2026-07-01"},
        {"from_month": JUNE, "to_start": "2026-07-01", "to_end": "2030-07-01"},
        {"from_month": "2026-01-01", "to_start": "2026-07-01", "to_end": "2026-07-01"},
    ]:
        assert client.post("/api/recurring/copy", json=body).status_code == 422, body
    assert client.get("/api/recurring/entries/9999").status_code == 404
    assert client.get("/api/recurring/grid", params={"year": 1900}).status_code == 422


# ---------------------------------------------------------------- statement matching
def test_statement_lines_match_by_category_pattern_and_halves(
    client: TestClient, db: Session
) -> None:
    acct = db.scalar(select(Account).where(Account.name.contains("Produbanco")))
    assert acct is not None
    condo = _template(
        client,
        name="Condo",
        category_id=_cat(db, "Condo Fee"),
        amount="269",
        match_pattern="condominio",
    )
    staff = _template(
        client,
        name="Empleada",
        category_id=_cat(db, "Empleada Salary"),
        amount="480",
        match_pattern="EMPLEADA",
        account_id=acct.account_id,
    )
    phone = _template(client, name="Phone", category_id=_cat(db, "Phone/Internet"), amount="27.12")
    _template(client, name="Water", category_id=_cat(db, "Water"), amount="40")
    client.post("/api/recurring/generate", json={"month": JUNE})

    _statement(
        client,
        [
            ("Jun 05", "1", "PAGO CONDOMINIO EDIFICIO", "-269.00"),
            ("Jun 15", "2", "TRANSFERENCIA EMPLEADA 1ERA", "-240.00"),
            ("Jun 30", "3", "TRANSFERENCIA EMPLEADA 2DA", "-240.50"),
            ("Jun 20", "4", "PAGO CONECEL", "-27.50"),
            ("Jun 21", "5", "PAGO CONECEL EXTRA", "-90.00"),
        ],
    )
    grid = _grid(client)
    # The uncategorized condo line qualifies through the pattern; the phone through its rule's
    # category; the two halves of the salary together.
    assert Decimal(_cell(grid["Condo"], 6)["actual"]) == Decimal("-269")
    assert (_cell(grid["Empleada"], 6)["lines"], Decimal(_cell(grid["Empleada"], 6)["actual"])) == (
        2,
        Decimal("-480.50"),
    )
    assert Decimal(_cell(grid["Phone"], 6)["actual"]) == Decimal("-27.50")
    assert _cell(grid["Water"], 6)["status"] == "planned"

    # The cell's details: lines, tolerance and candidates to link by hand.
    entry_id = _cell(grid["Phone"], 6)["entry_id"]
    detail = client.get(f"/api/recurring/entries/{entry_id}").json()
    assert [ln["description"] for ln in detail["lines"]] == ["PAGO CONECEL"]
    assert detail["lines"][0]["recurring_entry_id"] == entry_id
    assert Decimal(detail["tolerance"]) == Decimal("2.712")
    assert detail["candidates"][0]["description"] == "PAGO CONECEL EXTRA"
    line_id = detail["lines"][0]["transaction_id"]
    assert client.delete(f"/api/recurring/lines/{line_id}", headers=USER).status_code == 204
    assert client.delete(f"/api/recurring/lines/{line_id}").status_code == 404
    extra = detail["candidates"][0]["transaction_id"]
    linked = client.post(f"/api/recurring/entries/{entry_id}/lines", json={"transaction_id": extra})
    assert [ln["description"] for ln in linked.json()["lines"]] == ["PAGO CONECEL EXTRA"]
    assert db.scalar(
        select(ChangeLog).where(ChangeLog.row_id == extra, ChangeLog.reason == "Linked by hand")
    )
    # Skipping frees its lines; matching again doesn't touch a matched entry.
    client.patch(f"/api/recurring/entries/{entry_id}", json={"status": "skipped"})
    row = db.get(Transaction, extra)
    assert row is not None and row.recurring_entry_id is None
    assert client.post("/api/recurring/match").json() == {"count": 0}
    # Linking to a skipped entry plans it again; other months and missing lines are refused.
    client.post(f"/api/recurring/entries/{entry_id}/lines", json={"transaction_id": line_id})
    assert _cell(_grid(client)["Phone"], 6)["status"] == "matched"
    bad = client.post(f"/api/recurring/entries/{entry_id}/lines", json={"transaction_id": 99999})
    assert bad.status_code == 404
    client.post("/api/recurring/generate", json={"month": "2026-07-01"})
    july = _cell(_grid(client)["Phone"], 7)["entry_id"]
    other = client.post(f"/api/recurring/entries/{july}/lines", json={"transaction_id": line_id})
    assert other.status_code == 422
    assert condo["template_id"] != staff["template_id"] != phone["template_id"]


def test_matching_rules(db: Session, client: TestClient) -> None:
    acct = db.scalar(select(Account).where(Account.kind == "credit_card"))
    assert acct is not None
    _template(
        client, name="Card", category_id=_cat(db, "Water"), amount="100", account_id=acct.account_id
    )
    _template(client, name="Plain", category_id=_cat(db, "Water"), amount="100")
    client.post("/api/recurring/generate", json={"month": JUNE})
    _statement(
        client,
        [
            ("Jun 05", "1", "AGUA POTABLE", "-100.00"),  # no rule: uncategorized, no pattern
            ("Jun 06", "2", "AGUA POTABLE", "-150.00"),
        ],
    )
    lines = list(db.scalars(select(Transaction).where(Transaction.cash_month == date(2026, 6, 1))))
    for ln in lines:
        ln.category_id = _cat(db, "Water")
    db.commit()
    assert recurring.match(db, recurring.first(lines[0].txn_date)) == 1
    grid = _grid(client)
    # The card template is on another account: it can't take a Produbanco line.
    assert _cell(grid["Card"], 6)["status"] == "planned"
    assert Decimal(_cell(grid["Plain"], 6)["actual"]) == Decimal("-100")
    # Months, helpers.
    assert recurring.add_months(recurring.first(lines[0].txn_date), 7).isoformat() == "2027-01-01"
    assert recurring.match(db, recurring.add_months(lines[0].txn_date, 5)) == 0
    assert recurring.grid(db, 2025).rows == []


def test_a_transfer_matches_through_its_other_side(client: TestClient, db: Session) -> None:
    # BofA moves 25.00 from checking to savings; the template names the savings account, so the
    # checking line qualifies through the matched transfer's other side (F10).
    savings = db.scalar(select(Account).where(Account.name == "BofA Regular Savings"))
    assert savings is not None
    _template(
        client,
        name="To savings",
        category_id=_cat(db, "Between Own Accounts"),
        type="transfer",
        amount="25",
        start_month="2026-08-01",
        account_id=savings.account_id,
    )
    client.post("/api/recurring/generate", json={"month": "2026-08-01"})
    st = client.post(
        "/api/statements", files=[("files", ("b.pdf", s.bofa_full(), PDF))], headers=USER
    ).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    cell = _cell(_grid(client)["To savings"], 8)
    assert (cell["status"], Decimal(cell["actual"])) == ("matched", Decimal("-25"))
