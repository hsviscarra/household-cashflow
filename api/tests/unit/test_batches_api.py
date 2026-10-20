from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ImportBatch, LoadLog, RawLine, Transaction
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _upload(client: TestClient, name: str, data: bytes) -> dict:  # type: ignore[type-arg]
    resp = client.post("/api/statements", files=[("files", (name, data, PDF))], headers=USER)
    return resp.json()[0]["statement"]  # type: ignore[no-any-return]


def test_read_preview_approve_and_list(client: TestClient, db: Session) -> None:
    st = _upload(client, "co.pdf", s.capitalone_full())
    assert st["can_read"] is True and st["batch"] is None

    resp = client.post(f"/api/statements/{st['statement_file_id']}/read", headers=USER)
    assert resp.status_code == 200, resp.text
    b = resp.json()
    assert b["status"] == "preview" and b["tieout_ok"] is True
    assert all(c["ok"] for c in b["checks"])
    assert (b["new_lines"], b["duplicate_lines"], b["uncategorized"]) == (11, 0, 1)
    assert b["statement"]["batch"]["status"] == "preview"

    lines = {ln["description"]: ln for ln in b["lines"]}
    uber = lines["UBER EATS SAN JOSE"]
    assert (uber["category_path"], uber["merchant"], uber["person"]) == (
        "Dining / Food Delivery",
        "UBER EATS",
        "Lauren",
    )
    assert uber["country"] == "US"
    assert lines["DL RAPPI ECUADOR Guayaquil"]["country"] == "EC"
    assert lines["CAPITAL ONE MOBILE PYMT"]["type"] == "transfer"
    assert lines["INTEREST CHARGE ON PURCHASES"]["category_path"] == (
        "Financial Costs / Credit Card Interest"
    )
    refund = lines["AMAZON MKTPL*REFUND Amzn.com/bill WA"]
    assert (refund["type"], refund["category_path"]) == ("refund", "Shopping / Amazon")
    assert lines["NEW MERCHANT XYZ MIAMI FL"]["category_path"] is None
    needs = next(c for c in b["by_category"] if c["category_path"] == "Needs a category")
    assert Decimal(needs["amount"]) == Decimal("-40")

    listed = client.get("/api/statements").json()[0]
    assert listed["batch"]["batch_id"] == b["batch_id"]

    ok = client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER)
    assert ok.json() == {"batch_id": b["batch_id"], "loaded": 11, "skipped_duplicates": 0}
    assert client.post(f"/api/batches/{b['batch_id']}/approve").status_code == 409
    assert client.post(f"/api/statements/{st['statement_file_id']}/read").status_code == 409

    log = db.scalars(select(LoadLog).where(LoadLog.source == "statement")).one()
    assert log.rows_loaded == 11 and log.loaded_by == "hernan@example.com"

    sept = client.get("/api/transactions", params={"month": "2026-09-15"}).json()
    assert len(sept) == 9 and all(t["source"] == "statement" for t in sept)
    assert sept[0]["account_name"] == "Capital One Venture"
    octo = client.get("/api/transactions", params={"month": "2026-10-01", "source": "statement"})
    assert {t["description"] for t in octo.json()} == {
        "NEW MERCHANT XYZ MIAMI FL",
        "INTEREST CHARGE ON PURCHASES",
    }
    acct = sept[0]["account_id"]
    assert len(client.get("/api/transactions", params={"account_id": acct}).json()) == 11

    monthly = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    # September spending: card purchases less the refund; the card payment is a transfer.
    assert Decimal(monthly["2026-09-01"]["expenses"]) == Decimal("256.75")
    assert Decimal(monthly["2026-10-01"]["expenses"]) == Decimal("50")


def test_identical_lines_load_once_each_and_reloads_are_duplicates(
    client: TestClient, db: Session
) -> None:
    st = _upload(client, "co.pdf", s.capitalone_full())
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    client.post(f"/api/batches/{b['batch_id']}/approve")
    assert (
        db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.description_raw == "UBER EATS SAN JOSE")
        )
        == 2
    )

    # The bank re-issues the same statement as a different file: every line is a duplicate.
    again = _upload(client, "co-again.pdf", s.capitalone_full(extra_lines=[""]) + b"\n")
    b2 = client.post(f"/api/statements/{again['statement_file_id']}/read").json()
    assert (b2["new_lines"], b2["duplicate_lines"]) == (0, 11)
    res = client.post(f"/api/batches/{b2['batch_id']}/approve").json()
    assert (res["loaded"], res["skipped_duplicates"]) == (0, 11)


def test_rereading_a_preview_replaces_it_and_discard(client: TestClient, db: Session) -> None:
    st = _upload(client, "co.pdf", s.capitalone_full())
    sid = st["statement_file_id"]
    client.post(f"/api/statements/{sid}/read")
    second = client.post(f"/api/statements/{sid}/read").json()
    assert db.scalar(select(func.count()).select_from(ImportBatch)) == 1
    assert db.scalar(select(func.count()).select_from(RawLine)) == 11

    gone = client.post(f"/api/batches/{second['batch_id']}/reject", headers=USER).json()
    assert gone["status"] == "rejected" and gone["decided_by"] == "hernan@example.com"
    assert client.post(f"/api/batches/{second['batch_id']}/reject").status_code == 409
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_statement_that_does_not_tie_out_cannot_load(client: TestClient) -> None:
    st = _upload(client, "bad.pdf", s.capitalone_full(printed_total_delta="5.00"))
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is False
    bad = next(c for c in b["checks"] if not c["ok"])
    assert Decimal(bad["expected"]) - Decimal(bad["actual"]) == Decimal("5")
    resp = client.post(f"/api/batches/{b['batch_id']}/approve")
    assert resp.status_code == 409 and "tie out" in resp.json()["detail"]


def test_continuity_with_the_previous_statement(client: TestClient) -> None:
    aug = _upload(
        client,
        "aug.pdf",
        s.capitalone_full(
            period=("Aug 04, 2026", "Sep 03, 2026"),
            previous="900.00",
            payment="100.00",
            interest="0.00",
            lauren=[("Aug 10", "Aug 11", "UBER EATS SAN JOSE", "200.00")],
            hernan=[],
            payment_dates="Aug 20 Aug 21",
        ),
    )
    client.post(f"/api/statements/{aug['statement_file_id']}/read")
    sep = _upload(client, "sep.pdf", s.capitalone_full())  # opens at 1,000.00 = Aug closing
    b = client.post(f"/api/statements/{sep['statement_file_id']}/read").json()
    cont = b["checks"][-1]
    assert cont["name"].startswith("Opening balance = closing balance of the Sep 03, 2026")
    assert cont["ok"] is True

    gap = _upload(
        client,
        "gap.pdf",
        s.capitalone_full(
            previous="1234.00",
            period=("Oct 04, 2026", "Nov 03, 2026"),
            lauren=[],
            hernan=[],
            payment_dates="Oct 27 Oct 28",
        ),
    )
    g = client.post(f"/api/statements/{gap['statement_file_id']}/read").json()
    assert g["checks"][-1]["ok"] is False and g["tieout_ok"] is False


def test_read_errors(client: TestClient) -> None:
    assert client.post("/api/statements/999/read").status_code == 404
    assert client.get("/api/batches/999").status_code == 404
    assert client.post("/api/batches/999/approve").status_code == 404
    assert client.post("/api/batches/999/reject").status_code == 404
    bofa = _upload(client, "bofa.pdf", s.bofa())
    resp = client.post(f"/api/statements/{bofa['statement_file_id']}/read")
    assert resp.status_code == 422 and "not built yet" in resp.json()["detail"]
    assert bofa["can_read"] is False
    broken = _upload(client, "co-short.pdf", s.capitalone())  # detected, but no summary
    resp = client.post(f"/api/statements/{broken['statement_file_id']}/read")
    assert resp.status_code == 422 and "could not be read" in resp.json()["detail"]
