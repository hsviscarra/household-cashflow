"""F10: matching transfers between own accounts, the spending and cash views."""

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, ChangeLog, Transaction
from app.services import transfers
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
JUNE = "2026-06-01"


def _load(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/statements", files=[("files", (name, data, PDF))], headers=USER)
    st = resp.json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"], b["checks"]
    out: dict[str, Any] = client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER).json()
    return out


def _produbanco_june(lines: list[tuple[str, str, str, str]]) -> bytes:
    return s.produbanco_full(
        period="Del 01 Jun 2026 Al 30 Jun 2026", opening="2000.00", lines=lines
    )


def _txns(client: TestClient, month: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = client.get("/api/transactions", params={"month": month}).json()
    return out


def test_own_accounts_transfer_is_matched_on_approve(client: TestClient) -> None:
    _load(client, "bofa.pdf", s.bofa_full())
    txns = _txns(client, "2026-08-01")
    out = next(t for t in txns if t["amount"] == "-25.0000")
    into = next(t for t in txns if t["amount"] == "25.0000")
    assert out["transfer_group_id"] == into["transfer_group_id"] is not None
    assert out["transfer_with"]["account_name"] == "BofA Regular Savings"
    assert into["transfer_with"]["account_name"] == "BofA Adv Plus Banking"
    assert out["category_path"] == "Transfers / Between Own Accounts"
    # The Capital One payment (1,500) has no other side loaded: it is listed as unmatched.
    unmatched = client.get("/api/transfers/unmatched").json()
    assert [t["amount"] for t in unmatched] == ["-1500.0000"]
    assert client.get("/api/transfers/unmatched", params={"month": JUNE}).json() == []


def test_card_payment_pairs_bank_and_card_and_categorizes_an_unknown_leg(
    client: TestClient, db: Session
) -> None:
    # Diners (statement Jun 4 - Jul 3) shows the payment received: SU PAGO +650.00 on Jun 16.
    _load(client, "diners.pdf", s.diners_full())
    # Produbanco shows it leaving on Jun 15, as a plain interbank transfer nobody categorized.
    _load(
        client,
        "prod.pdf",
        _produbanco_june([("Jun 15", "1", "TRANSFERENCIA INTERBANCARIA B.L.", "-650.00")]),
    )
    bank = next(t for t in _txns(client, JUNE) if t["amount"] == "-650.0000")
    assert bank["type"] == "transfer" and bank["category_path"] == "Transfers / Card Payment"
    assert bank["category_source"] == "match"
    assert bank["transfer_with"]["account_kind"] == "credit_card"
    reasons = db.scalars(
        select(ChangeLog.reason).where(ChangeLog.row_id == bank["transaction_id"])
    ).all()
    assert set(reasons) == {"Matched transfer"}
    review = client.get("/api/review", params={"month": JUNE}).json()
    assert "TRANSFERENCIA INTERBANCARIA B.L." not in {g["merchant_key"] for g in review["groups"]}


def test_spending_and_cash_views(client: TestClient) -> None:
    _load(client, "diners.pdf", s.diners_full())
    _load(
        client,
        "prod.pdf",
        _produbanco_june(
            [
                ("Jun 15", "1", "PAGO TARJETA CREDITO PAGO DIRECTO B", "-650.00"),
                ("Jun 20", "2", "DEBITO VISA", "-40.00"),
            ]
        ),
    )
    spending = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    cash = {
        m["cash_month"]: m
        for m in client.get("/api/cashflow/monthly", params={"view": "cash"}).json()
    }
    # Spending: the card purchases in June and the bank debit; the payment is a transfer.
    june_card = Decimal("17.25") + Decimal("9.50") + Decimal("1038.59") + Decimal("45.50")
    assert Decimal(spending[JUNE]["expenses"]) == june_card + Decimal("40")
    assert Decimal(spending[JUNE]["card_payments"]) == 0
    # Cash: only bank money — the debit as spending and the payment to the card.
    assert Decimal(cash[JUNE]["expenses"]) == Decimal("40")
    assert Decimal(cash[JUNE]["card_payments"]) == Decimal("650")
    assert Decimal(cash[JUNE]["net"]) == Decimal("-690")
    assert client.get("/api/cashflow/monthly", params={"view": "other"}).status_code == 422


def test_a_chosen_category_is_never_overridden(client: TestClient, db: Session) -> None:
    _load(client, "diners.pdf", s.diners_full())
    _load(
        client,
        "prod.pdf",
        _produbanco_june([("Jun 15", "1", "TRANSFERENCIA INTERBANCARIA B.L.", "-650.00")]),
    )
    bank = next(t for t in _txns(client, JUNE) if t["amount"] == "-650.0000")
    group = bank["transfer_group_id"]
    # Unlink the pair, then call the bank line rent: it stays rent and unmatched.
    assert client.delete(f"/api/transfers/{group}", headers=USER).status_code == 204
    assert client.delete(f"/api/transfers/{group}").status_code == 404
    rent = db.scalar(select(Category).where(Category.name == "Housing"))
    assert rent is not None
    client.patch(
        f"/api/transactions/{bank['transaction_id']}", json={"category_id": rent.category_id}
    )
    assert client.post("/api/transfers/match").json() == {"pairs": 0}
    row = db.get(Transaction, bank["transaction_id"])
    assert row is not None and row.transfer_group_id is None
    # Calling it a card payment again re-pairs it with the Diners payment.
    card = next(t for t in _txns(client, JUNE) if t["description"].startswith("SU PAGO"))
    client.patch(
        f"/api/transactions/{bank['transaction_id']}", json={"category_id": card["category_id"]}
    )
    again = next(t for t in _txns(client, JUNE) if t["transaction_id"] == bank["transaction_id"])
    assert again["transfer_with"]["transaction_id"] == card["transaction_id"]


def test_recategorizing_a_matched_leg_unlinks_it(client: TestClient, db: Session) -> None:
    _load(client, "bofa.pdf", s.bofa_full())
    out = next(t for t in _txns(client, "2026-08-01") if t["amount"] == "-25.0000")
    other = db.scalar(select(Category).where(Category.name == "Other Expenses"))
    assert other is not None
    client.patch(
        f"/api/transactions/{out['transaction_id']}", json={"category_id": other.category_id}
    )
    legs = db.scalars(
        select(Transaction).where(Transaction.transfer_group_id == out["transfer_group_id"])
    )
    assert list(legs) == []


def test_matching_rules(db: Session, client: TestClient) -> None:
    _load(client, "bofa.pdf", s.bofa_full())
    # Too far apart, same account, or different amounts: no pair.
    rows = list(db.scalars(select(Transaction).where(Transaction.transfer_group_id.is_(None))))
    assert transfers.match(db).pairs == 0
    assert transfers.other_legs(db, rows) == {}
    assert transfers.other_legs(db, []) == {}
