"""ADR-034: where an Inbox line came from, and deleting a category."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.storage import LocalStore
from app.models import (
    Budget,
    Category,
    ChangeLog,
    MerchantRule,
    StatementFile,
    Transaction,
    TransferNote,
)
from app.services.line_source import mask
from tests.fixtures import statements as s
from tests.unit.test_classify_api import PDF, USER, _cat, _load, loaded  # noqa: F401


def test_mask_keeps_the_last_four_digits() -> None:
    assert mask("CTA 2201234567 CI 1712345678.") == "CTA ••••4567 CI ••••5678."
    assert mask("TRANSF 12-34-5678-90 REF 123") == "TRANSF ••••7890 REF 123"
    assert mask("Ago 3 600.00 2026 1234567.89") == "Ago 3 600.00 2026 1234567.89"


def test_inbox_lines_carry_the_statement_and_page(loaded: TestClient) -> None:  # noqa: F811
    groups = loaded.get("/api/review").json()["groups"]
    line = groups[0]["lines"][0]
    assert line["statement_file_id"] and line["page"] == 1
    assert "post_date" in line


def test_a_lines_source(loaded: TestClient, db: Session, store: LocalStore) -> None:  # noqa: F811
    line = loaded.get("/api/review").json()["groups"][0]["lines"][0]
    tid = line["transaction_id"]
    t = db.get(Transaction, tid)
    assert t is not None
    db.add(
        TransferNote(
            txn_date=t.txn_date,
            amount=t.amount,
            other_party="MARIA PEREZ",
            description="Arriendo octubre",
            transaction_id=tid,
            created_by="test",
        )
    )
    db.commit()
    src = loaded.get(f"/api/transactions/{tid}/source").json()
    assert src["statement_file_id"] == line["statement_file_id"] and src["page"] == 1
    assert src["bank"] == "produbanco" and src["file_name"] in ("jul.pdf", "aug.pdf")
    assert src["text"] and src["line_no"]
    marked = [a for a in src["around"] if a["is_line"]]
    assert len(marked) == 1 and marked[0]["line_no"] == src["line_no"]
    assert 1 < len(src["around"]) <= 7
    assert src["note_from"] == "MARIA PEREZ" and src["note"] == "Arriendo octubre"
    assert src["unreadable"] is False

    # A categorized line of the same merchant shows as "last time".
    other = loaded.get("/api/review").json()["groups"]
    key = next(g for g in other if any(ln["transaction_id"] == tid for ln in g["lines"]))
    assert len(key["lines"]) == 2
    loaded.post(
        "/api/review/resolve",
        json={
            "merchant_key": key["merchant_key"],
            "category_id": _cat(db, "Dining"),
            "transaction_ids": [key["lines"][1]["transaction_id"]],
        },
        headers=USER,
    )
    src = loaded.get(f"/api/transactions/{tid}/source").json()
    assert src["similar"] and src["similar"][0]["category_path"] == "Dining"

    # The stored PDF gone: the facts stay, the text around says it couldn't be read.
    sf = db.get(StatementFile, src["statement_file_id"])
    assert sf is not None
    (store.root / sf.blob_key).unlink()
    gone = loaded.get(f"/api/transactions/{tid}/source").json()
    assert gone["unreadable"] is True and gone["around"] == [] and gone["text"]
    assert loaded.get("/api/transactions/999999/source").status_code == 404


def test_a_staged_lines_source(client: TestClient) -> None:
    resp = client.post(
        "/api/statements", files=[("files", ("p.pdf", s.produbanco_full(), PDF))], headers=USER
    )
    st = resp.json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    groups = client.get(f"/api/batches/{b['batch_id']}/review").json()["groups"]
    line = groups[0]["lines"][0]
    assert line["statement_file_id"] == st["statement_file_id"] and line["page"] == 1
    src = client.get(f"/api/batches/{b['batch_id']}/lines/{line['transaction_id']}/source")
    assert src.status_code == 200, src.text
    assert any(a["is_line"] for a in src.json()["around"])
    assert client.get(f"/api/batches/{b['batch_id'] + 1}/lines/1/source").status_code == 404


def _sub(client: TestClient, db: Session, name: str, group: str = "Dining") -> int:
    out = client.post("/api/categories", json={"name": name, "parent_id": _cat(db, group)})
    assert out.status_code == 201, out.text
    return int(out.json()["category_id"])


def test_delete_an_unused_subcategory(client: TestClient, db: Session) -> None:
    cid = _sub(client, db, "Snacks")
    assert client.get(f"/api/categories/{cid}/uses").json()["total"] == 0
    out = client.delete(f"/api/categories/{cid}")
    assert out.status_code == 200 and out.json()["total"] == 0
    db.expire_all()
    assert db.get(Category, cid) is None
    assert client.delete(f"/api/categories/{cid}").status_code == 404


def _budget(category_id: int, amount: int) -> Budget:
    return Budget(
        month=date(2026, 7, 1),
        category_id=category_id,
        label="",
        type="expense",
        amount=Decimal(amount),
        source="excel_plan",
    )


def test_delete_moves_lines_rules_and_budgets(
    loaded: TestClient,  # noqa: F811
    db: Session,
) -> None:
    cid = _sub(loaded, db, "Snacks")
    keep = _sub(loaded, db, "Treats")
    group = loaded.get("/api/review").json()["groups"][0]
    r = loaded.post(
        "/api/review/resolve",
        json={"merchant_key": group["merchant_key"], "category_id": cid, "save_rule": True},
        headers=USER,
    )
    assert r.status_code == 200, r.text
    n = r.json()["categorized"]
    db.add_all(
        [
            _budget(cid, 10),
            _budget(keep, 5),
        ]
    )
    db.commit()
    uses = loaded.get(f"/api/categories/{cid}/uses").json()
    assert uses["lines"] == n and uses["rules"] == 1 and uses["budgets"] == 1

    blocked = loaded.delete(f"/api/categories/{cid}")
    assert blocked.status_code == 409 and "choose a category" in blocked.json()["detail"]
    income = _cat(db, "Other Income")
    assert loaded.delete(f"/api/categories/{cid}", params={"move_to": income}).status_code == 422
    assert loaded.delete(f"/api/categories/{cid}", params={"move_to": cid}).status_code == 422
    assert loaded.delete(f"/api/categories/{cid}", params={"move_to": 99999}).status_code == 404

    out = loaded.delete(f"/api/categories/{cid}", params={"move_to": keep}, headers=USER)
    assert out.status_code == 200, out.text
    assert out.json()["lines"] == n
    db.expire_all()
    assert db.get(Category, cid) is None
    moved = db.scalars(select(Transaction).where(Transaction.category_id == keep)).all()
    assert len(moved) == n
    assert db.scalars(select(MerchantRule).where(MerchantRule.category_id == keep)).first()
    [budget] = db.scalars(select(Budget).where(Budget.category_id == keep)).all()
    assert budget.amount == 15
    log = db.scalars(select(ChangeLog).where(ChangeLog.reason.like("Category Snacks deleted%")))
    logs = list(log)
    assert len(logs) == n and logs[0].changed_by == "hernan@example.com"


def test_a_group_with_subcategories_isnt_deleted(client: TestClient, db: Session) -> None:
    out = client.delete(f"/api/categories/{_cat(db, 'Dining')}")
    assert out.status_code == 409 and "subcategor" in out.json()["detail"]
