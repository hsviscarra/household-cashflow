"""Rules reach statements waiting for approval: a statement read before a rule existed gets it
when the rule is saved (Review or Settings), with "Apply rules again", and at approval."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, MerchantRule
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


def _two_months(client: TestClient) -> dict:  # type: ignore[type-arg]
    """July approved; August read (both carry DEBITO VISA) and waiting for approval."""
    jul = _read(client, "jul.pdf", s.produbanco_full())
    client.post(f"/api/batches/{jul['batch_id']}/approve", headers=USER)
    aug = s.produbanco_full(opening="243.40", period="Del 01 Ago 2026 Al 31 Ago 2026", lines=AUG)
    return _read(client, "aug.pdf", aug)


def _cat(db: Session, group: str, sub: str) -> int:
    parent = db.scalar(select(Category).where(Category.name == group, Category.parent_id.is_(None)))
    assert parent is not None
    child = db.scalar(
        select(Category).where(Category.name == sub, Category.parent_id == parent.category_id)
    )
    assert child is not None
    return child.category_id


def _line(batch: dict, description: str) -> dict:  # type: ignore[type-arg]
    return next(ln for ln in batch["lines"] if ln["description"] == description)  # type: ignore[no-any-return]


def test_a_rule_saved_in_review_reaches_waiting_statements(client: TestClient, db: Session) -> None:
    aug = _two_months(client)
    assert _line(aug, "DEBITO VISA")["category_path"] is None
    before = aug["uncategorized"]
    resp = client.post(
        "/api/review/resolve",
        json={
            "merchant_key": "DEBITO VISA",
            "category_id": _cat(db, "Groceries", "Supermarket"),
            "save_rule": True,
        },
        headers=USER,
    ).json()
    assert (resp["categorized"], resp["also_by_rule"], resp["waiting_by_rule"]) == (1, 0, 1)
    after = client.get(f"/api/batches/{aug['batch_id']}").json()
    assert _line(after, "DEBITO VISA")["category_path"] == "Groceries / Supermarket"
    assert after["uncategorized"] == before - 1

    client.post(f"/api/batches/{aug['batch_id']}/approve", headers=USER)
    txns = client.get("/api/transactions", params={"month": "2026-08-01"}).json()
    visa = next(t for t in txns if t["description"] == "DEBITO VISA")
    assert (visa["category_path"], visa["category_source"]) == ("Groceries / Supermarket", "rule")


def test_a_rule_saved_in_settings_reaches_loaded_and_waiting_lines(
    client: TestClient, db: Session
) -> None:
    aug = _two_months(client)
    body = {"pattern": "DEBITO VISA", "category_id": _cat(db, "Groceries", "Supermarket")}
    created = client.post("/api/merchant-rules", json=body, headers=USER).json()
    assert created["applied"] == 2  # July's loaded line and August's waiting one
    assert _line(client.get(f"/api/batches/{aug['batch_id']}").json(), "DEBITO VISA")[
        "category_path"
    ]
    # Turning a rule off applies nothing; listing reports nothing applied.
    off = client.patch(f"/api/merchant-rules/{created['rule_id']}", json={"is_active": False})
    assert off.json()["applied"] == 0
    assert all(r["applied"] == 0 for r in client.get("/api/merchant-rules").json())


def test_apply_rules_again_and_at_approval(client: TestClient, db: Session) -> None:
    aug = _two_months(client)
    # A rule that reached the database without being applied (as before this fix).
    db.add(MerchantRule(pattern="DEBITO VISA", category_id=_cat(db, "Groceries", "Supermarket")))
    db.commit()
    again = client.post(f"/api/batches/{aug['batch_id']}/apply-rules").json()
    assert again["categorized"] == 1
    assert _line(again["batch"], "DEBITO VISA")["category_path"] == "Groceries / Supermarket"
    assert client.post(f"/api/batches/{aug['batch_id']}/apply-rules").json()["categorized"] == 0

    # Another one, not applied by hand: approving applies it.
    db.add(
        MerchantRule(
            pattern="TRANSFERENCIA CTAS TERCEROS",
            category_id=_cat(db, "Transfers", "Between Own Accounts"),
        )
    )
    db.commit()
    client.post(f"/api/batches/{aug['batch_id']}/approve", headers=USER)
    txns = client.get("/api/transactions", params={"month": "2026-08-01"}).json()
    moved = next(t for t in txns if t["description"].startswith("TRANSFERENCIA CTAS"))
    assert (moved["category_path"], moved["type"]) == (
        "Transfers / Between Own Accounts",
        "transfer",
    )
    done = client.post(f"/api/batches/{aug['batch_id']}/apply-rules")
    assert done.status_code == 409
    assert client.post("/api/batches/999/apply-rules").status_code == 404
