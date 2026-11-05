"""ADR-023: people and transfer notes. A statement says "TRANSFERENCIA"; a note or a person's
name says whose money it is, and money held for someone shows on Debt & Net Worth."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Holding, Transaction, TransferNote
from app.services import people, status, transfers
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _cat(db: Session, group: str, name: str | None = None) -> int:
    parent = db.scalar(select(Category).where(Category.name == group, Category.parent_id.is_(None)))
    assert parent is not None
    if name is None:
        return parent.category_id
    c = db.scalar(
        select(Category).where(Category.parent_id == parent.category_id, Category.name == name)
    )
    assert c is not None
    return c.category_id


def _acct(db: Session, name: str) -> int:
    a = db.scalar(select(Account).where(Account.name == name))
    assert a is not None
    return a.account_id


def _line(
    db: Session,
    key: str,
    account: int,
    day: date,
    amount: str,
    text: str,
    category: int | None = None,
    source: str | None = None,
) -> Transaction:
    t = Transaction(
        natural_key=key,
        account_id=account,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=Decimal(amount),
        description_raw=text,
        type="expense" if Decimal(amount) < 0 else "income",
        category_id=category,
        category_source=source,
        source="statement",
        status="confirmed",
    )
    db.add(t)
    db.flush()
    return t


def _load(client: TestClient, data: bytes) -> None:
    resp = client.post("/api/statements", files=[("files", ("p.pdf", data, PDF))], headers=USER)
    st = resp.json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"], b["checks"]
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)


def test_a_person_tags_lines_by_their_texts(client: TestClient, db: Session) -> None:
    held = _cat(db, "Transfers", "Held for Others")
    bofa = _acct(db, "BofA Adv Plus Banking")
    rent = _cat(db, "Office Rent")
    _line(db, "in", bofa, date(2026, 7, 2), "12430", "TRANSFER LAUREN M STARK HERNA:RUBEN MIRANDA")
    _line(db, "zelle", bofa, date(2026, 7, 9), "-2000", "Zelle payment to ANDRES TORO Conf# x")
    _line(db, "mine", bofa, date(2026, 7, 9), "-80", "Zelle payment to ANDRES TORO", rent, "manual")
    _line(db, "other", bofa, date(2026, 7, 9), "-5", "SOMETHING ELSE")
    db.commit()

    resp = client.post(
        "/api/people",
        json={
            "name": "Rubén Miranda",
            "patterns": "RUBEN MIRANDA; andres toro",
            "category_id": held,
        },
        headers=USER,
    )
    assert resp.status_code == 201, resp.json()
    person = resp.json()
    assert person["patterns"] == "RUBEN MIRANDA; andres toro"
    assert person["category_path"] == "Transfers / Held for Others"
    assert person["lines"] == 3 and person["received"] == "12430.0000"
    rows = {t.natural_key: t for t in db.scalars(select(Transaction))}
    assert rows["in"].category_id == held and rows["in"].type == "transfer"
    assert rows["in"].category_source == "person"
    assert rows["zelle"].category_id == held
    # Chosen by hand: tagged with the person, but the category stays.
    assert rows["mine"].counterparty_id == person["counterparty_id"]
    assert rows["mine"].category_id == rent
    assert rows["other"].counterparty_id is None

    lines = client.get(f"/api/people/{person['counterparty_id']}/lines").json()
    assert [x["amount"] for x in lines] == ["-80.0000", "-2000.0000", "12430.0000"]

    assert client.post("/api/people", json={"name": "Rubén Miranda"}).status_code == 409
    assert client.post("/api/people", json={"name": "X", "patterns": "ab"}).status_code == 422
    assert client.post("/api/people", json={"name": "Y", "category_id": 99999}).status_code == 404
    assert client.post("/api/people", json={"name": "Z", "holding_id": 99999}).status_code == 404


def test_notes_name_anonymous_transfers(client: TestClient, db: Session) -> None:
    held = _cat(db, "Transfers", "Held for Others")
    ruben = client.post("/api/people", json={"name": "Rubén", "category_id": held}).json()
    produ = _acct(db, "Produbanco Ahorros Hernan")
    # Told before the statement: "received $561.89 for Rubén".
    note = client.post(
        "/api/transfer-notes",
        json={
            "txn_date": "2026-06-14",
            "direction": "received",
            "amount": "561.89",
            "account_id": produ,
            "counterparty_id": ruben["counterparty_id"],
            "description": "pago obra",
        },
        headers=USER,
    ).json()
    assert note["transaction_id"] is None and note["amount"] == "561.89"
    _load(
        client,
        s.produbanco_full(
            period="Del 01 Jun 2026 Al 30 Jun 2026",
            opening="2000.00",
            lines=[
                ("Jun 10", "1", "TRANSFERENCIA", "561.89"),  # too early: 5 days at most
                ("Jun 15", "2", "TRANSFERENCIA", "561.89"),
                ("Jun 16", "3", "TRANSFERENCIA", "-25.00"),
            ],
        ),
    )
    notes = client.get("/api/transfer-notes", params={"state": "matched", "days": 3660}).json()
    assert len(notes) == 1 and notes[0]["line_date"] == "2026-06-15"
    assert notes[0]["person"] == "Rubén"
    row = db.get(Transaction, notes[0]["transaction_id"])
    assert row is not None
    db.refresh(row)
    assert row.category_id == held and row.type == "transfer" and row.category_source == "note"
    assert row.counterparty_id == ruben["counterparty_id"]
    assert row.notes == "pago obra"

    # Told after the statement: matched at once; its own category wins over the person's.
    family = _cat(db, "Family Support", "Money to Family")
    after = client.post(
        "/api/transfer-notes",
        json={
            "txn_date": "2026-06-17",
            "direction": "sent",
            "amount": "25",
            "category_id": family,
            "other_party": "ANDRADE BAQUERO MARIA",
            "description": "para mamá",
        },
    ).json()
    assert after["line_date"] == "2026-06-16" and after["category_path"].startswith("Family")
    line = db.get(Transaction, after["transaction_id"])
    assert line is not None
    db.refresh(line)
    assert line.notes == "ANDRADE BAQUERO MARIA · para mamá" and line.category_id == family
    assert note["note_id"] != after["note_id"]
    assert client.get("/api/transfer-notes", params={"state": "open", "days": 3660}).json() == []

    bad = client.post(
        "/api/transfer-notes",
        json={"txn_date": "2026-06-17", "direction": "sent", "amount": "0"},
    )
    assert bad.status_code == 422
    missing = {"txn_date": "2026-06-17", "direction": "sent", "amount": "1", "account_id": 9999}
    assert client.post("/api/transfer-notes", json=missing).status_code == 404
    assert client.delete(f"/api/transfer-notes/{after['note_id']}").status_code == 204
    assert client.delete(f"/api/transfer-notes/{after['note_id']}").status_code == 404


def test_the_closest_line_and_one_note_per_reference(db: Session) -> None:
    produ = _acct(db, "Produbanco Ahorros Hernan")
    bofa = _acct(db, "BofA Adv Plus Banking")
    far = _line(db, "far", produ, date(2026, 8, 1), "-100", "TRANSFERENCIA")
    near = _line(db, "near", produ, date(2026, 8, 4), "-100", "TRANSFERENCIA")
    _line(db, "elsewhere", bofa, date(2026, 8, 5), "-100", "TRANSFER")
    db.commit()
    fields: dict[str, Any] = {
        "txn_date": date(2026, 8, 5),
        "amount": Decimal("-100"),
        "account_id": produ,
        "reference": "750716020900",
        "source": "email",
        "other_party": "NAPOLES TRANSPORT",
    }
    note, created = people.add_note(db, fields, "gmail")
    assert created and note.transaction_id == near.transaction_id
    again, created = people.add_note(db, fields, "gmail")
    assert not created and again.note_id == note.note_id
    second, _ = people.add_note(db, {**fields, "reference": "2"}, "gmail")
    assert second.transaction_id == far.transaction_id  # the nearer one is taken
    third, _ = people.add_note(db, {**fields, "reference": "3"}, "gmail")
    assert third.transaction_id is None
    people.unlink_note(db, second)
    assert second.transaction_id is None


def test_an_emailed_name_finds_the_person(db: Session) -> None:
    held = _cat(db, "Transfers", "Held for Others")
    p = people.create_person(
        db, {"name": "Rubén", "patterns": "INTELLIGENT ENTERPRISE", "category_id": held}, "h"
    )
    db.commit()
    note, _ = people.add_note(
        db,
        {
            "txn_date": date(2026, 10, 15),
            "amount": Decimal("228.35"),
            "other_party": "INTELLIGENT ENTERPRISE MANAG",
        },
        "gmail",
    )
    assert note.counterparty_id == p.counterparty_id
    assert people.person_for(db, "nobody") is None


def test_held_money_on_the_balance_sheet(client: TestClient, db: Session) -> None:
    held = _cat(db, "Transfers", "Held for Others")
    created = client.post(
        "/api/people",
        json={
            "name": "Rubén",
            "category_id": held,
            "new_balance": True,
            "opening_balance": "1000",
            "opening_as_of": "2026-06-30",
        },
    ).json()
    assert created["holding_name"] == "Holding for Rubén"
    bofa = _acct(db, "BofA Adv Plus Banking")
    _line(db, "before", bofa, date(2026, 6, 20), "500", "TRANSFER RUBEN")  # in the opening
    _line(db, "in", bofa, date(2026, 7, 2), "12430", "TRANSFER RUBEN")
    _line(db, "out", bofa, date(2026, 7, 9), "-3000", "Zelle payment to ANDRES TORO")
    db.commit()
    client.patch(
        f"/api/people/{created['counterparty_id']}", json={"patterns": "RUBEN; ANDRES TORO"}
    )
    sheet = client.get("/api/networth", params={"as_of": "2026-07-31"}).json()
    item = next(i for i in sheet["items"] if i["name"] == "Holding for Rubén")
    assert item["side"] == "liability" and item["value"] == "10430.0000"
    assert item["lines"] == "9430.0000"
    early = client.get("/api/networth", params={"as_of": "2026-06-30"}).json()
    assert (
        next(i for i in early["items"] if i["name"] == "Holding for Rubén")["value"] == "1000.0000"
    )
    # The same name twice is refused; linking anything but a personal loan too.
    dup = client.post("/api/people", json={"name": "Rubén 2", "new_balance": True})
    assert dup.status_code == 201
    clash = client.post(
        "/api/people", json={"name": "Rubén", "new_balance": True}
    )  # the person already exists
    assert clash.status_code == 409


def test_a_person_without_a_balance_item_has_no_balance(db: Session) -> None:
    assert people.balance_lines(db, 99999, None, date(2026, 7, 1)) == Decimal(0)


def test_received_and_paid_out_for_someone_are_not_a_transfer_pair(db: Session) -> None:
    held = _cat(db, "Transfers", "Held for Others")
    p = people.create_person(db, {"name": "Rubén", "patterns": "RUBEN", "category_id": held}, "h")
    produ = _acct(db, "Produbanco Ahorros Hernan")
    bofa = _acct(db, "BofA Adv Plus Banking")
    _line(db, "for him", produ, date(2026, 7, 2), "500", "TRANSFERENCIA RUBEN")
    out = _line(db, "own", bofa, date(2026, 7, 3), "-500", "ONLINE TRANSFER")
    out.type = "transfer"
    db.commit()
    people.tag_lines(db, "h")
    assert transfers.match(db, "h").pairs == 0
    rows = {t.natural_key: t for t in db.scalars(select(Transaction))}
    assert rows["for him"].counterparty_id == p.counterparty_id
    # The held line isn't "missing its other side"; the plain transfer still is.
    assert [t.natural_key for t in transfers.unmatched(db)] == ["own"]


def test_editing_and_deleting(client: TestClient, db: Session) -> None:
    produ = _acct(db, "Produbanco Ahorros Hernan")
    row = _line(db, "x", produ, date(2026, 7, 2), "-40", "TRANSFERENCIA")
    db.commit()
    p = client.post("/api/people", json={"name": "Gabriel"}).json()
    edited = client.patch(
        f"/api/transactions/{row.transaction_id}", json={"counterparty_id": p["counterparty_id"]}
    )
    assert edited.status_code == 200 and edited.json()["counterparty_id"] == p["counterparty_id"]
    assert (
        client.patch(
            f"/api/transactions/{row.transaction_id}", json={"counterparty_id": 999}
        ).status_code
        == 404
    )
    renamed = client.patch(
        f"/api/people/{p['counterparty_id']}",
        json={"name": "Gabriel M", "is_active": False, "notes": "loan"},
    ).json()
    assert (
        renamed["name"] == "Gabriel M" and not renamed["is_active"] and renamed["notes"] == "loan"
    )
    other = client.post("/api/people", json={"name": "Ana"}).json()
    assert (
        client.patch(
            f"/api/people/{other['counterparty_id']}", json={"name": "Gabriel M"}
        ).status_code
        == 409
    )
    assert (
        client.patch(f"/api/people/{other['counterparty_id']}", json={"name": " "}).status_code
        == 422
    )
    car = Holding(name="Car", side="asset", holding_class="vehicle")
    db.add(car)
    db.commit()
    refused = client.patch(
        f"/api/people/{other['counterparty_id']}", json={"holding_id": car.holding_id}
    )
    assert refused.status_code == 422
    people.add_note(
        db,
        {
            "txn_date": date(2026, 7, 2),
            "amount": Decimal("-40"),
            "counterparty_id": p["counterparty_id"],
        },
        "h",
    )
    assert client.delete(f"/api/people/{p['counterparty_id']}").status_code == 204
    db.expire_all()
    line = db.get(Transaction, row.transaction_id)
    assert line is not None and line.counterparty_id is None
    assert all(n.counterparty_id is None for n in db.scalars(select(TransferNote)))
    assert client.delete(f"/api/people/{p['counterparty_id']}").status_code == 404
    names = [x["name"] for x in client.get("/api/people").json()]
    assert names == ["Ana"]
    assert client.post("/api/transfer-notes/match").json() == {"matched": 0, "tagged": 0}


def test_data_status_lists_notes_without_a_line(client: TestClient, db: Session) -> None:
    produ = _acct(db, "Produbanco Ahorros Hernan")
    _load(
        client,
        s.produbanco_full(
            period="Del 01 Jun 2026 Al 30 Jun 2026",
            opening="2000.00",
            lines=[("Jun 15", "2", "TRANSFERENCIA", "100.00")],
        ),
    )
    people.add_note(
        db, {"txn_date": date(2026, 6, 10), "amount": Decimal("99"), "account_id": produ}, "h"
    )
    # After the statement's end: not yet expected.
    people.add_note(
        db, {"txn_date": date(2026, 6, 29), "amount": Decimal("5"), "account_id": produ}, "h"
    )
    st = status.month_status(db, today=date(2026, 7, 20))
    june = next(m for m in st.months if m.month == date(2026, 6, 1))
    notes = [i for i in june.items if i.kind == "note"]
    assert [i.text for i in notes] == ["1 transfer note has no statement line"]
    assert notes[0].link == "/people"
    assert people.open_notes(db, date(2026, 7, 1))[0].amount == Decimal("99")


def test_a_shared_payment_is_split(client: TestClient, db: Session) -> None:
    """Lopes pays Rubén's work and Hernan's in one transfer: the note says Rubén's share."""
    held = _cat(db, "Transfers", "Held for Others")
    consulting = _cat(db, "Other Income", "Consulting & Freelance")
    ruben = client.post(
        "/api/people", json={"name": "Rubén", "category_id": held, "new_balance": True}
    ).json()
    produ = _acct(db, "Produbanco Ahorros Hernan")
    row = _line(db, "lopes", produ, date(2026, 10, 20), "1065", "TRANSFERENCIA")
    db.commit()
    body = {
        "txn_date": "2026-10-20",
        "direction": "received",
        "amount": "1065",
        "account_id": produ,
        "counterparty_id": ruben["counterparty_id"],
        "category_id": consulting,
        "share": "852",
        "description": "Lopes agosto-septiembre",
    }
    note = client.post("/api/transfer-notes", json=body).json()
    assert note["transaction_id"] == row.transaction_id and Decimal(note["share"]) == 852
    db.expire_all()
    parts = sorted(
        db.scalars(
            select(Transaction).where(Transaction.parent_transaction_id == row.transaction_id)
        ),
        key=lambda t: t.amount,
    )
    assert [(p.amount, p.category_id) for p in parts] == [
        (Decimal("213.0000"), consulting),
        (Decimal("852.0000"), held),
    ]
    assert parts[1].counterparty_id == ruben["counterparty_id"] and parts[1].type == "transfer"
    assert parts[0].type == "income" and parts[0].counterparty_id is None
    sheet = client.get("/api/networth", params={"as_of": "2026-10-31"}).json()
    item = next(i for i in sheet["items"] if i["name"] == "Holding for Rubén")
    assert item["value"] == "852.0000"

    # A share needs the person's category, a category for the rest, and to fit the amount.
    bad = [
        {**body, "share": "1065"},
        {**body, "category_id": None},
        {**body, "counterparty_id": None},
    ]
    for b in bad:
        assert client.post("/api/transfer-notes", json=b).status_code == 422, b


def test_the_preview_shows_what_notes_and_people_will_do(client: TestClient, db: Session) -> None:
    held = _cat(db, "Transfers", "Held for Others")
    consulting = _cat(db, "Other Income", "Consulting & Freelance")
    ruben = client.post(
        "/api/people", json={"name": "Rubén", "patterns": "NAPOLES", "category_id": held}
    ).json()
    produ = _acct(db, "Produbanco Ahorros Hernan")
    client.post(
        "/api/transfer-notes",
        json={
            "txn_date": "2026-06-14",
            "direction": "received",
            "amount": "561.89",
            "account_id": produ,
            "counterparty_id": ruben["counterparty_id"],
            "description": "pago obra",
        },
    )
    client.post(
        "/api/transfer-notes",
        json={
            "txn_date": "2026-06-20",
            "direction": "received",
            "amount": "1065.00",
            "counterparty_id": ruben["counterparty_id"],
            "category_id": consulting,
            "share": "852",
        },
    )
    resp = client.post(
        "/api/statements",
        files=[
            (
                "files",
                (
                    "p.pdf",
                    s.produbanco_full(
                        period="Del 01 Jun 2026 Al 30 Jun 2026",
                        opening="2000.00",
                        lines=[
                            ("Jun 15", "2", "TRANSFERENCIA", "561.89"),
                            ("Jun 18", "3", "PAGO NAPOLES TRANSPORT", "-150.00"),
                            ("Jun 21", "4", "TRANSFERENCIA", "1065.00"),
                            ("Jun 22", "5", "TRANSFERENCIA", "-9.00"),
                        ],
                    ),
                    PDF,
                ),
            )
        ],
        headers=USER,
    )
    st = resp.json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    lines = {line["txn_date"]: line for line in b["lines"]}
    note = lines["2026-06-15"]
    assert (note["hint_source"], note["hint_person"], note["hint_text"]) == (
        "note",
        "Rubén",
        "pago obra",
    )
    assert note["category_path"] == "Transfers / Held for Others" and note["type"] == "transfer"
    person = lines["2026-06-18"]
    assert (person["hint_source"], person["hint_person"]) == ("person", "Rubén")
    assert person["category_path"] == "Transfers / Held for Others"
    shared = lines["2026-06-21"]
    assert shared["hint_source"] == "note" and Decimal(shared["hint_share"]) == 852
    assert shared["category_path"] != "Transfers / Held for Others"  # split at approval
    assert lines["2026-06-22"]["hint_source"] is None
    paths = {c["category_path"] for c in b["by_category"]}
    assert "Transfers / Held for Others" in paths

    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    db.expire_all()
    rows = {
        t.txn_date: t
        for t in db.scalars(select(Transaction).where(Transaction.parent_transaction_id.is_(None)))
    }
    assert rows[date(2026, 6, 15)].category_source == "note"
    assert rows[date(2026, 6, 15)].counterparty_id == ruben["counterparty_id"]
    assert rows[date(2026, 6, 18)].counterparty_id == ruben["counterparty_id"]
    parts = db.scalars(
        select(Transaction).where(
            Transaction.parent_transaction_id == rows[date(2026, 6, 21)].transaction_id
        )
    ).all()
    assert sorted(p.amount for p in parts) == [Decimal("213.0000"), Decimal("852.0000")]
