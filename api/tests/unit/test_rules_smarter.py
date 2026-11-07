"""ADR-042: a rule also sets the person and the merchant name, and rules suggest themselves after
the same merchant is categorized the same way twice by hand. Synthetic data only."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transaction
from tests.fixtures import statements as s
from tests.unit.test_rules_waiting import AUG, USER, _cat, _line, _read

SEP = [("Sep 4", "9", "DEBITO VISA", "-30.00")]


def _visa(db: Session) -> list[Transaction]:
    return list(db.scalars(select(Transaction).where(Transaction.description_raw == "DEBITO VISA")))


def test_suggested_rule_then_person_and_merchant(client: TestClient, db: Session) -> None:
    jul = _read(client, "jul.pdf", s.produbanco_full())
    client.post(f"/api/batches/{jul['batch_id']}/approve", headers=USER)
    aug_pdf = s.produbanco_full(
        opening="243.40", period="Del 01 Ago 2026 Al 31 Ago 2026", lines=AUG
    )
    aug = _read(client, "aug.pdf", aug_pdf)
    client.post(f"/api/batches/{aug['batch_id']}/approve", headers=USER)
    assert client.get("/api/merchant-rules/suggestions").json() == []

    # Categorized by hand twice the same way: offered as a rule.
    super_id = _cat(db, "Groceries", "Supermarket")
    visa = _visa(db)
    assert len(visa) == 2
    for t in visa:
        t.category_id, t.category_source, t.person = super_id, "manual", "Joint"
    db.commit()
    [sug] = client.get("/api/merchant-rules/suggestions").json()
    assert (sug["pattern"], sug["times"], sug["person"]) == ("DEBITO VISA", 2, "Joint")
    assert sug["category_path"] == "Groceries / Supermarket"

    # One line categorized differently: no longer offered.
    visa[0].category_id = _cat(db, "Transfers", "Between Own Accounts")
    db.commit()
    assert client.get("/api/merchant-rules/suggestions").json() == []
    visa[0].category_id = super_id
    db.commit()

    body = {
        "pattern": sug["pattern"],
        "category_id": super_id,
        "set_person": "Lauren",
        "merchant_name": "Visa debit",
    }
    rule = client.post("/api/merchant-rules", json=body, headers=USER)
    assert rule.status_code == 201, rule.text
    out = rule.json()
    assert (out["set_person"], out["merchant_name"]) == ("Lauren", "Visa debit")
    assert client.get("/api/merchant-rules/suggestions").json() == []  # a rule covers it now
    db.expire_all()  # lines categorized by hand are never touched by a rule
    assert {(t.person, t.category_source) for t in _visa(db)} == {("Joint", "manual")}

    # A new statement gets the person and the name at staging.
    sep_pdf = s.produbanco_full(
        opening="831.40", period="Del 01 Sep 2026 Al 30 Sep 2026", lines=SEP
    )
    sep = client.post(
        "/api/statements", files=[("files", ("sep.pdf", sep_pdf, "application/pdf"))], headers=USER
    ).json()[0]["statement"]
    batch = client.post(f"/api/statements/{sep['statement_file_id']}/read").json()
    line = _line(batch, "DEBITO VISA")
    assert line["category_path"] == "Groceries / Supermarket"
    client.post(f"/api/batches/{batch['batch_id']}/approve", headers=USER)
    db.expire_all()
    new = [t for t in _visa(db) if t.category_source == "rule"]
    assert [(t.person, t.merchant) for t in new] == [("Lauren", "Visa debit")]

    # Clearing the actions; bad person refused.
    patched = client.patch(
        f"/api/merchant-rules/{out['rule_id']}", json={"set_person": None, "merchant_name": None}
    ).json()
    assert patched["set_person"] is None and patched["merchant_name"] is None
    bad = client.post("/api/merchant-rules", json={**body, "set_person": "Bob"}, headers=USER)
    assert bad.status_code == 422
