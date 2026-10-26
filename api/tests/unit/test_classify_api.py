"""F9: review queue, resolving a merchant and its rule, edits with history, splits, suggestions."""

from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Category, ChangeLog, MerchantRule, MerchantSuggestion
from app.services import classify, suggest
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
JUL = "2026-07-01"


def _load(client: TestClient, name: str, data: bytes) -> None:
    resp = client.post("/api/statements", files=[("files", (name, data, PDF))], headers=USER)
    st = resp.json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"], b["checks"]
    client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)


def _cat(db: Session, path: str) -> int:
    group, _, sub = path.partition("/")
    parent = db.scalar(select(Category).where(Category.name == group, Category.parent_id.is_(None)))
    assert parent is not None
    if not sub:
        return parent.category_id
    child = db.scalar(
        select(Category).where(Category.name == sub, Category.parent_id == parent.category_id)
    )
    assert child is not None
    return child.category_id


@pytest.fixture
def loaded(client: TestClient) -> TestClient:
    _load(client, "jul.pdf", s.produbanco_full())
    aug = [
        ("Ago 3", "9", "TRANSFERENCIA CTAS TERCEROS BCA ENL", "+600.00"),
        ("Ago 5", "8", "DEBITO VISA", "-12.00"),
    ]
    _load(
        client,
        "aug.pdf",
        s.produbanco_full(opening="243.40", period="Del 01 Ago 2026 Al 31 Ago 2026", lines=aug),
    )
    return client


def test_merchant_key_groups_references_away() -> None:
    assert classify.merchant_key("MICROSOFT*123456 MSBILL.I") == classify.merchant_key(
        "MICROSOFT*987654 MSBILL.I"
    )
    assert classify.merchant_key("Uber   Eats #12 San Jose") == "UBER EATS SAN JOSE"
    assert classify.merchant_key(
        "ZELLE PAYMENT TO TEST PERSON CONF# LW8SYSS8Y"
    ) == classify.merchant_key("Zelle payment to Test Person Conf# ZZ9Q81XYQ")
    assert (
        classify.merchant_key("ZELLE PAYMENT TO TEST PERSON CONF# X1")
        == "ZELLE PAYMENT TO TEST PERSON"
    )
    # Plain words stay, even long ones.
    assert classify.merchant_key("SUPERMAXI CUMBAYA") == "SUPERMAXI CUMBAYA"


def test_review_groups_a_months_unknown_merchants(loaded: TestClient) -> None:
    r = loaded.get("/api/review", params={"month": JUL}).json()
    keys = {g["merchant_key"]: g for g in r["groups"]}
    assert set(keys) == {
        "TRANSFERENCIA INTERBANCARIA B.L.",
        "TRANSFERENCIA CTAS TERCEROS BCA ENL",
        "DEBITO VISA",
    }
    assert keys["TRANSFERENCIA CTAS TERCEROS BCA ENL"]["total"] == "600.0000"
    assert r["uncategorized_lines"] == 3 and r["suggestions_available"] is False
    # Biggest money first.
    assert r["groups"][0]["merchant_key"] == "TRANSFERENCIA CTAS TERCEROS BCA ENL"
    # All months when no month is given (August adds lines to two of the merchants).
    assert loaded.get("/api/review").json()["uncategorized_lines"] == 5


def test_resolve_saves_a_rule_and_applies_it_to_other_months(
    loaded: TestClient, db: Session
) -> None:
    rent = _cat(db, "Office Rent")
    resp = loaded.post(
        "/api/review/resolve",
        json={
            "merchant_key": "TRANSFERENCIA CTAS TERCEROS BCA ENL",
            "category_id": rent,
            "transaction_ids": None,
            "save_rule": True,
            "amount_min": "500",
        },
        headers=USER,
    ).json()
    # Both months' lines are in the group (the queue spans months); one rule saved.
    assert resp["categorized"] == 2 and resp["rule_id"] and resp["also_by_rule"] == 0
    rule = db.get(MerchantRule, resp["rule_id"])
    assert rule is not None and rule.amount_min == Decimal("500")
    txns = loaded.get("/api/transactions", params={"month": JUL}).json()
    line = next(t for t in txns if t["description"] == "TRANSFERENCIA CTAS TERCEROS BCA ENL")
    assert (line["category_path"], line["type"], line["category_source"]) == (
        "Office Rent",
        "income",
        "manual",
    )
    history = loaded.get(f"/api/transactions/{line['transaction_id']}/history").json()
    assert {h["column_name"] for h in history} == {"category_id"}
    assert history[0]["changed_by"] == "hernan@example.com"

    # A new statement line the rule matches is categorized when the statement is read.
    sep = [("Sep 2", "7", "TRANSFERENCIA CTAS TERCEROS BCA ENL", "+600.00")]
    _load(
        loaded,
        "sep.pdf",
        s.produbanco_full(opening="831.40", period="Del 01 Sep 2026 Al 30 Sep 2026", lines=sep),
    )
    sep_line = loaded.get("/api/transactions", params={"month": "2026-09-01"}).json()[0]
    assert sep_line["category_path"] == "Office Rent" and sep_line["category_source"] == "rule"


def test_saved_rule_catches_other_uncategorized_lines(loaded: TestClient, db: Session) -> None:
    groceries = _cat(db, "Groceries/Supermarket")
    # Only the July line chosen; the rule then categorizes August's line too.
    jul_line = loaded.get("/api/review", params={"month": JUL}).json()
    visa = next(g for g in jul_line["groups"] if g["merchant_key"] == "DEBITO VISA")
    resp = loaded.post(
        "/api/review/resolve",
        json={
            "merchant_key": "DEBITO VISA",
            "category_id": groceries,
            "transaction_ids": [visa["lines"][0]["transaction_id"]],
            "save_rule": True,
            "pattern": "DEBITO VISA",
            "match_type": "starts_with",
        },
    ).json()
    assert (resp["categorized"], resp["also_by_rule"]) == (1, 1)
    assert loaded.get("/api/review").json()["uncategorized_lines"] == 3


def test_resolve_errors(loaded: TestClient, db: Session) -> None:
    rent = _cat(db, "Office Rent")
    body: dict[str, Any] = {"merchant_key": "NOPE", "category_id": rent}
    assert loaded.post("/api/review/resolve", json=body).status_code == 409
    body["merchant_key"] = "DEBITO VISA"
    body["category_id"] = 99999
    assert loaded.post("/api/review/resolve", json=body).status_code == 404
    body.update(category_id=rent, pattern="(", match_type="regex")
    assert loaded.post("/api/review/resolve", json=body).status_code == 422
    body.update(pattern=None, match_type="contains", amount_min="10", amount_max="5")
    assert loaded.post("/api/review/resolve", json=body).status_code == 422
    # Without a rule nothing else changes.
    body.update(amount_min=None, amount_max=None, save_rule=False)
    done = loaded.post("/api/review/resolve", json=body).json()
    assert done["rule_id"] is None and done["categorized"] == 2


def test_edit_a_line_and_its_history(loaded: TestClient, db: Session) -> None:
    txns = loaded.get("/api/transactions", params={"month": JUL}).json()
    fee = next(t for t in txns if t["amount"] == "-0.4100")
    dining = _cat(db, "Dining/Restaurants & Cafés")
    out = loaded.patch(
        f"/api/transactions/{fee['transaction_id']}",
        json={"category_id": dining, "notes": "lunch, not a fee", "person": "Lauren"},
        headers=USER,
    ).json()
    assert out["category_path"] == "Dining / Restaurants & Cafés"
    assert (out["type"], out["category_source"], out["person"]) == ("expense", "manual", "Lauren")
    cols = [
        h["column_name"]
        for h in loaded.get(f"/api/transactions/{fee['transaction_id']}/history").json()
    ]
    assert sorted(cols) == ["category_id", "notes", "person", "type"]

    # Money in on a spending category is a refund.
    income = next(t for t in txns if t["amount"] == "600.0000")
    out = loaded.patch(
        f"/api/transactions/{income['transaction_id']}", json={"category_id": dining}
    ).json()
    assert out["type"] == "refund"

    assert loaded.patch("/api/transactions/999999", json={"notes": "x"}).status_code == 404
    bad = loaded.patch(f"/api/transactions/{fee['transaction_id']}", json={"category_id": None})
    assert bad.status_code == 422
    assert (
        loaded.patch(
            f"/api/transactions/{fee['transaction_id']}", json={"category_id": 99999}
        ).status_code
        == 404
    )
    assert loaded.get("/api/transactions/999999/history").status_code == 404


def test_split_a_line_counts_its_parts(loaded: TestClient, db: Session) -> None:
    txns = loaded.get("/api/transactions", params={"month": JUL}).json()
    card = next(t for t in txns if t["amount"] == "-1080.0000")  # a card payment (transfer)
    before = {m["cash_month"]: m for m in loaded.get("/api/cashflow/monthly").json()}
    housing = _cat(db, "Housing/Home Maintenance")
    dining = _cat(db, "Dining/Restaurants & Cafés")
    url = f"/api/transactions/{card['transaction_id']}/split"

    bad = {
        "parts": [
            {"amount": "-1000.00", "category_id": housing},
            {"amount": "-70.00", "category_id": dining},
        ]
    }
    assert "add up to" in loaded.put(url, json=bad).json()["detail"]
    wrong_sign = {
        "parts": [
            {"amount": "-1100.00", "category_id": housing},
            {"amount": "20.00", "category_id": dining},
        ]
    }
    assert loaded.put(url, json=wrong_sign).status_code == 422
    unknown = {
        "parts": [
            {"amount": "-1000.00", "category_id": 99999},
            {"amount": "-80.00", "category_id": dining},
        ]
    }
    assert loaded.put(url, json=unknown).status_code == 404

    good = {
        "parts": [
            {"amount": "-1000.00", "category_id": housing, "notes": "roof"},
            {"amount": "-80.00", "category_id": dining},
        ]
    }
    parts = loaded.put(url, json=good, headers=USER).json()
    assert [p["category_source"] for p in parts] == ["split", "split"]
    assert {p["parent_transaction_id"] for p in parts} == {card["transaction_id"]}
    listed = loaded.get("/api/transactions", params={"month": JUL}).json()
    assert next(t for t in listed if t["transaction_id"] == card["transaction_id"])["parts"] == 2

    # The views count the parts (expenses now) instead of the transfer.
    after = {m["cash_month"]: m for m in loaded.get("/api/cashflow/monthly").json()}
    assert Decimal(after[JUL]["expenses"]) - Decimal(before[JUL]["expenses"]) == Decimal("1080")

    # A part can't be split again; splitting again replaces the parts.
    nested = f"/api/transactions/{parts[0]['transaction_id']}/split"
    assert loaded.put(nested, json=good).status_code == 422
    assert len(loaded.put(url, json=good).json()) == 2
    assert loaded.delete(url).status_code == 204
    assert loaded.delete(url).status_code == 404
    back = {m["cash_month"]: m for m in loaded.get("/api/cashflow/monthly").json()}
    assert back[JUL]["expenses"] == before[JUL]["expenses"]
    cols = [
        h["column_name"]
        for h in loaded.get(f"/api/transactions/{card['transaction_id']}/history").json()
    ]
    assert cols.count("split") >= 3  # made, replaced, removed


def test_rules_carry_amount_ranges(client: TestClient, db: Session) -> None:
    hit = client.get(
        "/api/merchant-rules/test",
        params={"description": "PAGO IESS BANCA EN LINEA", "amount": "-104.11"},
    ).json()["rule"]
    assert (
        hit["category_path"] == "Household Staff / Empleada IESS"
        and hit["amount_max"] == "299.9900"
    )
    hit = client.get(
        "/api/merchant-rules/test",
        params={"description": "PAGO IESS BANCA EN LINEA", "amount": "-505.19"},
    ).json()["rule"]
    assert hit["category_path"] == "Housing / Mortgage BIESS"
    # Without an amount a ranged rule doesn't match.
    none = client.get("/api/merchant-rules/test", params={"description": "PAGO IESS"}).json()
    assert none["rule"] is None

    cid = _cat(db, "Pets")
    bad = client.post(
        "/api/merchant-rules",
        json={"pattern": "VET", "category_id": cid, "amount_min": "50", "amount_max": "10"},
    )
    assert bad.status_code == 422
    made = client.post(
        "/api/merchant-rules", json={"pattern": "VET", "category_id": cid, "amount_max": "10"}
    ).json()
    patched = client.patch(f"/api/merchant-rules/{made['rule_id']}", json={"amount_min": "20"})
    assert patched.status_code == 422
    again = client.patch(f"/api/merchant-rules/{made['rule_id']}", json={"amount_min": "5"})
    assert Decimal(again.json()["amount_min"]) == Decimal(5)


def test_deleting_a_rule_keeps_the_categories_it_gave(loaded: TestClient, db: Session) -> None:
    rule = db.scalar(select(MerchantRule).where(MerchantRule.pattern == "PAGO IESS"))
    assert rule is not None
    assert loaded.delete(f"/api/merchant-rules/{rule.rule_id}").status_code == 204
    txns = loaded.get("/api/transactions", params={"month": JUL}).json()
    iess = [t for t in txns if t["description"] == "PAGO IESS BANCA EN LINEA"]
    assert all(t["category_path"] for t in iess)


# ---------------- suggestions ----------------
@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    get_settings.cache_clear()


def test_suggest_without_a_key_is_off(loaded: TestClient) -> None:
    resp = loaded.post("/api/review/suggest", params={"month": JUL})
    assert resp.status_code == 503 and "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_suggestions_are_stored_shown_and_accepted(
    loaded: TestClient, db: Session, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Any] = []

    def fake(asked: list[suggest.Asked], categories: list[str]) -> list[suggest.Answer]:
        sent.append((asked, categories))
        keys = {x.merchant_key for x in asked} | {"UNKNOWN"}
        return [a for a in ANSWERS if a.merchant_key in keys]

    ANSWERS = [
        suggest.Answer("DEBITO VISA", "groceries/Supermarket", Decimal("0.62"), "card debit"),
        suggest.Answer(
            "TRANSFERENCIA CTAS TERCEROS BCA ENL", "Office Rent", Decimal("1.7"), "rent"
        ),
        suggest.Answer("UNKNOWN", "Office Rent", Decimal("0.9"), "ignored"),
        suggest.Answer("TRANSFERENCIA INTERBANCARIA B.L.", "Not A Category", Decimal("0.5"), "x"),
    ]

    monkeypatch.setattr(suggest, "call_claude", fake)
    monkeypatch.setattr(suggest, "PER_CALL", 2)  # three merchants: two requests
    out = loaded.post("/api/review/suggest", params={"month": JUL}).json()
    assert (out["asked"], out["suggested"], out["model"]) == (3, 2, "claude-haiku-5-5")
    assert [len(a) for a, _ in sent] == [2, 1]
    asked, categories = sent[0]
    # Only description, amount, date and the bank leave the server.
    assert set(asked[0].lines[0]) == {
        "description",
        "amount",
        "date",
        "bank",
        "country",
        "card_or_account",
    }
    assert "Office Rent" in categories and "Groceries" not in categories  # leaves only

    r = loaded.get("/api/review", params={"month": JUL}).json()
    groups = {g["merchant_key"]: g for g in r["groups"]}
    assert r["suggestions_available"] is True
    assert groups["DEBITO VISA"]["suggestion"]["confidence"] == "0.620"
    assert groups["TRANSFERENCIA CTAS TERCEROS BCA ENL"]["suggestion"]["confidence"] == "1.000"
    assert groups["TRANSFERENCIA INTERBANCARIA B.L."]["suggestion"] is None

    # Merchants with a suggestion aren't asked again.
    assert loaded.post("/api/review/suggest", params={"month": JUL}).json()["asked"] == 1

    s_ = groups["DEBITO VISA"]["suggestion"]
    done = loaded.post(
        "/api/review/resolve",
        json={
            "merchant_key": "DEBITO VISA",
            "category_id": s_["category_id"],
            "from_suggestion": True,
            "save_rule": False,
        },
    ).json()
    assert done["categorized"] == 2
    assert (
        db.scalar(
            select(MerchantSuggestion).where(MerchantSuggestion.merchant_key == "DEBITO VISA")
        )
        is None
    )
    line = next(
        t
        for t in loaded.get("/api/transactions", params={"month": JUL}).json()
        if t["description"] == "DEBITO VISA"
    )
    assert line["category_source"] == "suggestion"
    log = db.scalars(select(ChangeLog).where(ChangeLog.row_id == line["transaction_id"])).all()
    assert any("suggestion" in c.reason for c in log)


def test_nothing_to_suggest(client: TestClient, with_key: None) -> None:
    assert client.post("/api/review/suggest").json()["asked"] == 0


def test_suggest_failure_is_reported(
    loaded: TestClient, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_a: object) -> list[suggest.Answer]:
        raise suggest.SuggestError("Claude could not be reached: APIConnectionError.")

    monkeypatch.setattr(suggest, "call_claude", broken)
    resp = loaded.post("/api/review/suggest")
    assert resp.status_code == 502 and "could not be reached" in resp.json()["detail"]


def test_call_claude_reads_the_structured_answer(
    with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import anthropic

    calls: list[dict[str, Any]] = []
    stop = ["end_turn"]
    answer = (
        '{"suggestions": [{"merchant_key": "A", "category_path": "Pets", '
        '"confidence": 0.8, "reason": "vet"}]}'
    )

    class FakeMessages:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return SimpleNamespace(
                stop_reason=stop[0],
                content=[
                    SimpleNamespace(type="thinking", thinking="..."),
                    SimpleNamespace(type="text", text=answer),
                ],
            )

    class FakeClient:
        def __init__(self, **_kw: Any) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    got = suggest.call_claude([suggest.Asked("A", [{"description": "VET"}])], ["Pets"])
    assert got == [suggest.Answer("A", "Pets", Decimal("0.8"), "vet")]
    fmt = calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    item = fmt["schema"]["properties"]["suggestions"]["items"]["properties"]
    assert item["category_path"]["enum"] == ["Pets"] and item["merchant_key"]["enum"] == ["A"]
    assert calls[0]["model"] == "claude-haiku-5-5"
    # Haiku thinks first and that counts toward max_tokens: low effort, room for the answer.
    assert calls[0]["output_config"]["effort"] == "low" and calls[0]["max_tokens"] >= 16000

    stop[0] = "max_tokens"
    with pytest.raises(suggest.SuggestError, match="cut off"):
        suggest.call_claude([suggest.Asked("A", [])], ["Pets"])
    stop[0] = "refusal"
    with pytest.raises(suggest.SuggestError, match="declined"):
        suggest.call_claude([suggest.Asked("A", [])], ["Pets"])
    stop[0] = "end_turn"

    answer = "not json"
    with pytest.raises(suggest.SuggestError, match="could not be read"):
        suggest.call_claude([suggest.Asked("A", [])], ["Pets"])

    class Failing(FakeMessages):
        def create(self, **kwargs: Any) -> Any:
            raise anthropic.APIConnectionError(request=SimpleNamespace())  # type: ignore[arg-type]

    class FailingClient(FakeClient):
        def __init__(self, **_kw: Any) -> None:
            self.messages = Failing()

    monkeypatch.setattr(anthropic, "Anthropic", FailingClient)
    with pytest.raises(suggest.SuggestError, match="could not be reached"):
        suggest.call_claude([suggest.Asked("A", [])], ["Pets"])


ITEM = '{"merchant_key": "A", "category_path": "Pets", "confidence": 0.8, "reason": "vet"}'
LOOSE = '{"merchant": "A", "category": "Pets", "confidence": "0.8", "reason": "vet"}'


@pytest.mark.parametrize(
    "text",
    [
        '{"suggestions": [' + ITEM + "]}",
        '```json\n{"suggestions": [' + ITEM + "]}\n```",
        "Here you go: [" + LOOSE + "]",
        '{"results": [' + ITEM + ", 7]}",
    ],
)
def test_parse_answer_tolerates_wrapping(text: str) -> None:
    assert suggest.parse_answer(text) == [suggest.Answer("A", "Pets", Decimal("0.8"), "vet")]


def test_parse_answer_skips_bad_items_and_reports_nothing_usable() -> None:
    mixed = (
        '[{"merchant_key": "A", "category_path": "Pets", "confidence": "x"}, {"merchant_key": "B"}]'
    )
    assert suggest.parse_answer(mixed) == [suggest.Answer("A", "Pets", Decimal(0), "")]
    assert suggest.parse_answer('{"suggestions": []}') == []
    for bad, why in [
        ("no json here", "no JSON"),
        ('{"suggestions": 3}', "no list"),
        ('[{"merchant_key": "B"}]', "no usable item"),
    ]:
        with pytest.raises(ValueError, match=why):
            suggest.parse_answer(bad)
