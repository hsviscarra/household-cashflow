"""F23 part 2: categorizing a statement on its page before approval, Claude's suggestions for one
statement, and accepting the likely ones in one click (statement page and Review)."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Category, MerchantRule, MerchantSuggestion
from app.services import suggest
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
AUG = [
    ("Ago 3", "9", "TRANSFERENCIA CTAS TERCEROS BCA ENL", "+600.00"),
    ("Ago 5", "8", "DEBITO VISA", "-12.00"),
]


def _read(client: TestClient, name: str, data: bytes) -> dict:  # type: ignore[type-arg]
    resp = client.post("/api/statements", files=[("files", (name, data, PDF))], headers=USER)
    st = resp.json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"], b["checks"]
    return b  # type: ignore[no-any-return]


@pytest.fixture
def aug(client: TestClient) -> dict:  # type: ignore[type-arg]
    """July approved; August read and waiting for approval (both have DEBITO VISA)."""
    jul = _read(client, "jul.pdf", s.produbanco_full())
    client.post(f"/api/batches/{jul['batch_id']}/approve", headers=USER)
    data = s.produbanco_full(opening="243.40", period="Del 01 Ago 2026 Al 31 Ago 2026", lines=AUG)
    return _read(client, "aug.pdf", data)


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    get_settings.cache_clear()


def _cat(db: Session, group: str, sub: str | None = None) -> int:
    parent = db.scalar(select(Category).where(Category.name == group, Category.parent_id.is_(None)))
    assert parent is not None
    if sub is None:
        return parent.category_id
    child = db.scalar(
        select(Category).where(Category.name == sub, Category.parent_id == parent.category_id)
    )
    assert child is not None
    return child.category_id


def _loaded(client: TestClient, description: str, month: str = "2026-08-01") -> dict:  # type: ignore[type-arg]
    txns = client.get("/api/transactions", params={"month": month}).json()
    return next(t for t in txns if t["description"] == description)  # type: ignore[no-any-return]


def test_a_statements_lines_are_grouped_by_merchant(client: TestClient, aug: dict) -> None:  # type: ignore[type-arg]
    r = client.get(f"/api/batches/{aug['batch_id']}/review").json()
    keys = {g["merchant_key"]: g for g in r["groups"]}
    assert "DEBITO VISA" in keys and r["month"] is None
    visa = keys["DEBITO VISA"]["lines"]
    staged = {ln["stg_id"] for ln in aug["lines"] if ln["description"] == "DEBITO VISA"}
    assert {ln["transaction_id"] for ln in visa} == staged  # the staged line's id
    assert r["uncategorized_lines"] == aug["uncategorized"]
    assert client.get("/api/batches/999/review").status_code == 404


def test_categorize_on_the_statement_page_with_a_rule(
    client: TestClient,
    db: Session,
    aug: dict,  # type: ignore[type-arg]
) -> None:
    bid = aug["batch_id"]
    groceries = _cat(db, "Groceries", "Supermarket")
    resp = client.post(
        f"/api/batches/{bid}/resolve",
        json={"merchant_key": "DEBITO VISA", "category_id": groceries, "save_rule": True},
        headers=USER,
    ).json()
    # This statement's line, plus July's loaded one through the new rule.
    assert (resp["categorized"], resp["also_by_rule"], resp["waiting_by_rule"]) == (1, 1, 0)
    assert db.get(MerchantRule, resp["rule_id"]) is not None
    batch = client.get(f"/api/batches/{bid}").json()
    visa = next(ln for ln in batch["lines"] if ln["description"] == "DEBITO VISA")
    assert visa["category_path"] == "Groceries / Supermarket"
    groups = client.get(f"/api/batches/{bid}/review").json()["groups"]
    assert "DEBITO VISA" not in {g["merchant_key"] for g in groups}

    client.post(f"/api/batches/{bid}/approve", headers=USER)
    line = _loaded(client, "DEBITO VISA")
    # Chosen by a person on the statement page: says "manual", not "by rule".
    assert (line["category_path"], line["category_source"]) == ("Groceries / Supermarket", "manual")
    jul = _loaded(client, "DEBITO VISA", "2026-07-01")
    assert (jul["category_path"], jul["category_source"]) == ("Groceries / Supermarket", "rule")


def test_categorize_without_a_rule_and_errors(
    client: TestClient,
    db: Session,
    aug: dict,  # type: ignore[type-arg]
) -> None:
    bid = aug["batch_id"]
    rent = _cat(db, "Office Rent")
    body = {"merchant_key": "TRANSFERENCIA CTAS TERCEROS BCA ENL", "category_id": rent}
    resp = client.post(f"/api/batches/{bid}/resolve", json=body | {"save_rule": False}).json()
    assert (resp["categorized"], resp["rule_id"]) == (1, None)
    batch = client.get(f"/api/batches/{bid}").json()
    moved = next(ln for ln in batch["lines"] if ln["description"].startswith("TRANSFERENCIA CTAS"))
    assert (moved["category_path"], moved["type"]) == ("Office Rent", "income")

    # Already done, unknown category, unknown statement, bad pattern.
    assert client.post(f"/api/batches/{bid}/resolve", json=body).status_code == 409
    other = {"merchant_key": "DEBITO VISA"}
    assert (
        client.post(f"/api/batches/{bid}/resolve", json=other | {"category_id": 9999}).status_code
        == 404
    )
    assert (
        client.post("/api/batches/999/resolve", json=other | {"category_id": rent}).status_code
        == 404
    )
    bad = other | {"category_id": rent, "pattern": "(", "match_type": "regex"}
    assert client.post(f"/api/batches/{bid}/resolve", json=bad).status_code == 422
    assert db.scalar(select(MerchantRule).where(MerchantRule.pattern == "(")) is None

    client.post(f"/api/batches/{bid}/approve", headers=USER)
    done = client.post(f"/api/batches/{bid}/resolve", json=other | {"category_id": rent})
    assert done.status_code == 409 and "already approved" in done.json()["detail"]


def test_ask_claude_about_one_statement_and_accept_the_likely_ones(
    client: TestClient,
    db: Session,
    aug: dict,  # type: ignore[type-arg]
    with_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bid = aug["batch_id"]
    asked: list[str] = []

    def fake(
        groups: list[suggest.Asked], categories: list[str], descriptions: dict[str, str]
    ) -> list[suggest.Answer]:
        asked.extend(g.merchant_key for g in groups)
        sure = {"DEBITO VISA": ("Groceries / Supermarket", Decimal("0.92"))}
        return [
            suggest.Answer(
                g.merchant_key, *(sure.get(g.merchant_key, ("Office Rent", Decimal("0.55")))), "x"
            )
            for g in groups
        ]

    monkeypatch.setattr(suggest, "call_claude", fake)
    out = client.post(f"/api/batches/{bid}/suggest").json()
    assert out["asked"] == len(asked) and "DEBITO VISA" in asked
    review = client.get(f"/api/batches/{bid}/review").json()
    visa = next(g for g in review["groups"] if g["merchant_key"] == "DEBITO VISA")
    assert visa["suggestion"]["category_path"] == "Groceries / Supermarket"

    # Only the likely one (>= 0.8) is accepted, with its rule; the 0.55 ones wait for a person.
    done = client.post(f"/api/batches/{bid}/accept-suggestions", headers=USER).json()
    assert (done["merchants"], done["lines"], done["also_by_rule"]) == (1, 1, 1)  # + July's
    left = client.get(f"/api/batches/{bid}/review").json()["groups"]
    assert "DEBITO VISA" not in {g["merchant_key"] for g in left}
    assert all(g["suggestion"] for g in left)
    assert (
        db.scalar(
            select(MerchantSuggestion).where(MerchantSuggestion.merchant_key == "DEBITO VISA")
        )
        is None
    )

    # A lower bar takes the rest.
    rest = client.post(
        f"/api/batches/{bid}/accept-suggestions", params={"min_confidence": "0.5"}
    ).json()
    assert rest["merchants"] == len(left)
    assert client.get(f"/api/batches/{bid}/review").json()["groups"] == []

    client.post(f"/api/batches/{bid}/approve", headers=USER)
    assert _loaded(client, "DEBITO VISA")["category_source"] == "suggestion"
    assert client.post(f"/api/batches/{bid}/accept-suggestions").status_code == 409
    assert client.post("/api/batches/999/accept-suggestions").status_code == 404
    assert client.post("/api/batches/999/suggest").status_code == 404
    assert (
        client.post(
            f"/api/batches/{bid}/accept-suggestions", params={"min_confidence": "2"}
        ).status_code
        == 422
    )


def test_suggestions_for_a_statement_need_a_key(client: TestClient, aug: dict) -> None:  # type: ignore[type-arg]
    resp = client.post(f"/api/batches/{aug['batch_id']}/suggest")
    assert resp.status_code == 503


def test_accept_likely_suggestions_on_review(client: TestClient, db: Session, aug: dict) -> None:  # type: ignore[type-arg]
    # Loaded July lines with stored suggestions (as the Review page's "Ask Claude" leaves them).
    db.add(
        MerchantSuggestion(
            merchant_key="DEBITO VISA",
            category_id=_cat(db, "Groceries", "Supermarket"),
            confidence=Decimal("0.85"),
            reason="card debit",
            model="test",
        )
    )
    db.add(
        MerchantSuggestion(
            merchant_key="TRANSFERENCIA INTERBANCARIA B.L.",
            category_id=_cat(db, "Office Rent"),
            confidence=Decimal("0.4"),
            reason="unsure",
            model="test",
        )
    )
    db.commit()
    done = client.post(
        "/api/review/accept-suggestions", params={"month": "2026-07-01"}, headers=USER
    ).json()
    # July's line and, through the rule, August's waiting one.
    assert (done["merchants"], done["lines"], done["also_by_rule"]) == (1, 1, 1)
    jul = _loaded(client, "DEBITO VISA", "2026-07-01")
    assert (jul["category_path"], jul["category_source"]) == (
        "Groceries / Supermarket",
        "suggestion",
    )
    left = client.get("/api/review", params={"month": "2026-07-01"}).json()["groups"]
    assert "TRANSFERENCIA INTERBANCARIA B.L." in {g["merchant_key"] for g in left}


def test_one_merchant_two_categories_on_the_statement_page(
    client: TestClient,
    db: Session,
) -> None:
    lines = [("Ago 5", "8", "DEBITO VISA", "-12.00"), ("Ago 9", "7", "DEBITO VISA", "-80.00")]
    jul = _read(client, "jul.pdf", s.produbanco_full())
    client.post(f"/api/batches/{jul['batch_id']}/approve", headers=USER)
    data = s.produbanco_full(opening="243.40", period="Del 01 Ago 2026 Al 31 Ago 2026", lines=lines)
    bid = _read(client, "aug.pdf", data)["batch_id"]
    visa = next(
        g
        for g in client.get(f"/api/batches/{bid}/review").json()["groups"]
        if g["merchant_key"] == "DEBITO VISA"
    )
    small = next(ln["transaction_id"] for ln in visa["lines"] if ln["amount"] == "-12.0000")
    body = {
        "merchant_key": "DEBITO VISA",
        "category_id": _cat(db, "Groceries", "Supermarket"),
        "transaction_ids": [small],
        "save_rule": False,
    }
    assert client.post(f"/api/batches/{bid}/resolve", json=body).json()["categorized"] == 1
    left = client.get(f"/api/batches/{bid}/review").json()["groups"]
    rest = next(g for g in left if g["merchant_key"] == "DEBITO VISA")
    assert [ln["amount"] for ln in rest["lines"]] == ["-80.0000"]  # the other one waits
