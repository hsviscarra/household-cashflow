"""ADR-077: Claude is asked with what the app already knows about a line, and the bank sync
categorizes what no rule knew."""

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Account, AppSetting, Transaction
from app.services import suggest
from tests.unit.test_bank_sync import USER, feed  # noqa: F401
from tests.unit.test_line_context import _add
from tests.unit.test_shopping import _invoice


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    get_settings.cache_clear()


def test_claude_is_asked_with_what_the_app_knows(
    client: TestClient, db: Session, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = db.scalars(select(Account).limit(1)).one()
    db.add(
        AppSetting(
            setting_key=f"card-purpose:{a.account_id}",
            setting_value=json.dumps({"for": "Juliana", "usual": ["EINSTEIN"]}),
            updated_by="test",
        )
    )
    _add(db, a, date(2026, 9, 22), "-89.69", "ALICUOTA OFICINA", cat="Office Alícuota")
    line = _add(db, a, date(2026, 10, 22), "-89.69", "TRANSFERENCIA INTERNET 123")
    line.person = "Lauren"
    _add(db, a, date(2026, 10, 10), "-12.50", "PAYPHONE TIENDA")
    _invoice(db, date(2026, 10, 9), "CORPORACION FAVORITA C.A.", [("Leche", "1", "12.50")])
    by_hand = _add(db, a, date(2026, 10, 3), "-7.00", "PANADERIA AMBATO", cat="Supermarket")
    by_hand.category_source = "manual"
    db.commit()

    sent: list[Any] = []

    def fake(
        asked: list[suggest.Asked],
        categories: list[str],
        descriptions: dict[str, str],
        examples: list[dict[str, str]],
    ) -> list[suggest.Answer]:
        sent.append((asked, examples))
        return []

    monkeypatch.setattr(suggest, "call_claude", fake)
    assert suggest.suggest(db)[0] == 2
    asked, examples = sent[0]
    by_key = {x.merchant_key: x.context for x in asked}
    transfer = next(v for k, v in by_key.items() if k.startswith("TRANSFERENCIA"))
    assert transfer["person"] == "Lauren"
    assert transfer["card_purpose"] == "kept for Juliana; its usual merchants: EINSTEIN"
    [same] = transfer["same_amount_before"]
    assert same["description"] == "ALICUOTA OFICINA" and same["category"].endswith("Alícuota")
    assert "invoice" not in transfer
    shop = next(v for k, v in by_key.items() if k.startswith("PAYPHONE"))
    assert shop["invoice"] == {"seller": "CORPORACION FAVORITA C.A.", "products": ["Leche"]}
    assert [e["description"] for e in examples] == ["PANADERIA AMBATO"]
    assert examples[0]["category"].endswith("Supermarket")


def test_call_claude_sends_context_and_examples(monkeypatch: pytest.MonkeyPatch) -> None:
    got: dict[str, Any] = {}

    class Messages:
        def create(self, **kw: Any) -> Any:
            got.update(json.loads(kw["messages"][0]["content"]))

            block = SimpleNamespace(type="text", text='{"suggestions": []}')
            return SimpleNamespace(stop_reason="end_turn", content=[block])

    class Client:
        def __init__(self, **_kw: Any) -> None:
            self.messages = Messages()

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", Client)
    asked = [
        suggest.Asked("A", [{"description": "A"}], {"person": "Lauren"}),
        suggest.Asked("B", [{"description": "B"}]),
    ]
    examples = [{"description": "X", "amount": "-1", "category": "Pets"}]
    assert suggest.call_claude(asked, ["Pets"], None, examples) == []
    assert got["merchants"][0]["context"] == {"person": "Lauren"}
    assert "context" not in got["merchants"][1]
    assert got["examples"] == examples


def test_bank_sync_asks_claude_about_new_merchants(
    client: TestClient,
    db: Session,
    feed: list[tuple[str, dict[str, str]]],  # noqa: F811
    with_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake(
        asked: list[suggest.Asked], categories: list[str], *_a: object
    ) -> list[suggest.Answer]:
        leaf = next(c for c in categories if c.endswith("Rideshare"))
        return [suggest.Answer(x.merchant_key, leaf, Decimal("0.97"), "ride") for x in asked]

    monkeypatch.setattr(suggest, "call_claude", fake)
    card = db.scalars(select(Account).where(Account.institution == "Capital One")).first()
    assert card is not None
    client.put("/api/bank-sync/link", json={"sync_id": "ACT-CAP1", "account_id": card.account_id})
    out = client.post("/api/bank-sync/run", params={"today": "2026-09-16"}, headers=USER).json()
    assert out["ran"] is True and out["added"] == 1
    assert out["auto"] == {"merchants": 1, "lines": 1}
    db.expire_all()
    uber = db.scalars(select(Transaction).where(Transaction.description_raw == "UBER")).one()
    assert uber.category_id is not None and uber.category_source == "suggestion"
