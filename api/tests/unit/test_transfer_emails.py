"""ADR-023: the banks' transfer notices become transfer notes. Synthetic emails only."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion import transfer_email as te
from app.models import Account, Category, Transaction, TransferNote
from tests.fixtures import transfer_emails as e

TOKEN = "i" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def inbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("INBOX_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("INBOX_TOKEN")
    get_settings.cache_clear()


@pytest.fixture
def pichincha(db: Session) -> Account:
    a = Account(
        name="Banco Pichincha",
        institution="Banco Pichincha",
        kind="savings",
        owner="Hernan",
        country="EC",
        last4="0800",
    )
    db.add(a)
    db.commit()
    return a


def test_reading_the_notices() -> None:
    sent = te.parse(*e.PRODU_SENT)
    assert sent == te.Notice(
        "Produbanco",
        "sent",
        Decimal("408.74"),
        None,
        "NAPOLES TRANSPORT SA",
        "5511",
        "Flete obra",
        "750716020900",
        date(2026, 9, 8),
    )
    got = te.parse(*e.PRODU_RECEIVED)
    assert got is not None
    assert (got.direction, got.amount, got.our_last4, got.other_party) == (
        "received",
        Decimal("1065.00"),
        "3721",
        "INTELLIGENT ENTERPRISE MANAG",
    )
    assert got.description == "SOLICITUD DEL ORDENANTE" and got.day == date(2026, 10, 15)
    assert got.reference == "261015036021550815"
    credited = te.parse(*e.PRODU_CREDITED)
    assert credited is not None and credited.other_party == "PERSONA DE PRUEBA"
    assert credited.our_last4 == "3721" and credited.day is None  # month/day order unclear
    other = te.parse(*e.PRODU_TO_SOMEONE_ELSE)
    assert other is not None and other.bank == "Banco Pichincha" and other.our_last4 == "1704"
    pich = te.parse(*e.PICHINCHA_SENT)
    assert pich == te.Notice(
        "Banco Pichincha",
        "sent",
        Decimal("25.00"),
        "0800",
        "PERSONA DESTINO DE PRUEBA",
        "9635",
        "Para mamá",
        "32942365",
        date(2026, 10, 14),
    )
    copy = te.parse(*e.PICHINCHA_COPY_NOT_OURS)
    assert copy is not None and copy.our_last4 == "9635" and copy.description is None
    received = te.parse(*e.PICHINCHA_RECEIVED)
    assert received is not None and received.amount == Decimal("1237.09")
    assert received.other_party == "Ruben Prueba" and received.description == "Saldo octubre"
    assert received.day == date(2026, 10, 20)
    assert te.parse(*e.NOT_A_TRANSFER) is None
    assert te.parse("Transferencia acreditada Produbanco", "Monto: $0.00") is None
    assert te.parse("Transferencia rara Produbanco", "*Monto:* $5.00") is None
    assert te.parse("NOTIFICACION BANCO PICHINCHA", "Realizaste una transferencia.") is None
    assert te.parse("NOTIFICACION BANCO PICHINCHA", "Transferencia. Cuenta acreditada: x") is None


def _post(client: TestClient, email: tuple[str, str], day: str = "2026-09-08") -> dict:  # type: ignore[type-arg]
    resp = client.post(
        "/api/inbox/transfer",
        json={"subject": email[0], "body": email[1], "sender": "bank@x.ec", "sent_on": day},
        headers=AUTH,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


def test_notices_become_notes(
    inbox: None, client: TestClient, db: Session, pichincha: Account
) -> None:
    produ = db.scalar(select(Account).where(Account.name == "Produbanco Ahorros Hernan"))
    assert produ is not None
    line = Transaction(
        natural_key="lopes",
        account_id=produ.account_id,
        txn_date=date(2026, 10, 16),
        cash_month=date(2026, 10, 1),
        amount=Decimal("1065"),
        description_raw="TRANSFERENCIA",
        type="income",
        source="statement",
        status="confirmed",
    )
    db.add(line)
    db.commit()

    sent = _post(client, e.PRODU_SENT)
    assert sent["status"] == "noted" and "NAPOLES TRANSPORT SA" in sent["message"]
    matched = _post(client, e.PRODU_RECEIVED, "2026-10-15")
    assert matched["status"] == "matched"
    assert _post(client, e.PRODU_RECEIVED, "2026-10-15")["status"] == "duplicate"
    assert _post(client, e.PRODU_SENT_OWN)["status"] == "skipped"  # to own Pichincha 0800
    assert _post(client, e.PRODU_TO_SOMEONE_ELSE)["status"] == "skipped"  # a relative's account
    assert _post(client, e.PICHINCHA_COPY_NOT_OURS)["status"] == "skipped"
    assert _post(client, e.PICHINCHA_SENT)["status"] == "noted"
    assert _post(client, e.PICHINCHA_RECEIVED)["status"] == "noted"
    assert _post(client, e.PRODU_CREDITED)["status"] == "noted"
    assert _post(client, e.NOT_A_TRANSFER)["status"] == "skipped"

    notes = {n.reference: n for n in db.scalars(select(TransferNote))}
    assert set(notes) == {
        "Produbanco:750716020900",
        "Produbanco:261015036021550815",
        "Banco Pichincha:32942365",
        "Banco Pichincha:33000001",
        "Produbanco:119383287",
    }
    napoles = notes["Produbanco:750716020900"]
    assert napoles.amount == Decimal("-408.74") and napoles.account_id == produ.account_id
    assert napoles.source == "email" and napoles.created_by == "gmail (bank@x.ec)"
    lopes = notes["Produbanco:261015036021550815"]
    assert lopes.transaction_id == line.transaction_id
    db.refresh(line)
    assert line.notes == "INTELLIGENT ENTERPRISE MANAG · SOLICITUD DEL ORDENANTE"
    credited = notes["Produbanco:119383287"]
    assert credited.txn_date == date(2026, 9, 8)  # no readable day in the text: the email's
    assert notes["Banco Pichincha:32942365"].account_id == pichincha.account_id
    # Only the note's fields are kept: no account numbers beyond the account it points to.
    assert all("9635" not in (n.description or "") for n in notes.values())


def test_a_known_person_gets_the_note(
    inbox: None, client: TestClient, db: Session, pichincha: Account
) -> None:
    held = db.scalar(select(Category).where(Category.name == "Held for Others"))
    assert held is not None
    client.post(
        "/api/people",
        json={"name": "Rubén", "patterns": "RUBEN PRUEBA", "category_id": held.category_id},
    )
    _post(client, e.PICHINCHA_RECEIVED)
    note = db.scalar(select(TransferNote))
    assert note is not None and note.counterparty_id is not None


def test_the_token_guards_it(inbox: None, client: TestClient) -> None:
    body = {"subject": "x", "body": "y", "sent_on": "2026-10-01"}
    assert client.post("/api/inbox/transfer", json=body).status_code == 401
    assert client.post("/api/inbox/transfer", json=body, headers=AUTH).status_code == 200


def test_produbanco_sent_needs_one_account_of_hernan(db: Session) -> None:
    from app.services import people

    notice = te.parse(*e.PRODU_SENT)
    assert notice is not None
    db.add(
        Account(
            name="Produbanco 2",
            institution="Produbanco",
            kind="checking",
            owner="Hernan",
            country="EC",
            last4="1111",
        )
    )
    db.commit()
    result = people.note_from_email(db, notice, date(2026, 9, 8), "gmail")
    assert result.status == "skipped"
