"""ADR-051: where's the money. Synthetic data only."""

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "hernan@example.com"}


def test_where_is_the_money(client: TestClient) -> None:
    empty = client.get("/api/reconcile", params={"from": "2026-08-01", "to": "2026-09-01"})
    assert empty.status_code == 200
    body = empty.json()
    assert Decimal(body["kept"]) == 0 and body["accounts"] == []

    st = client.post(
        "/api/statements", files=[("files", ("bofa.pdf", s.bofa_full(), PDF))], headers=USER
    ).json()[0]["statement"]
    batch = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    if batch.get("status") == "preview":
        client.post(f"/api/batches/{batch['batch_id']}/approve", headers=USER)

    body = client.get("/api/reconcile", params={"from": "2026-08-01", "to": "2026-09-01"}).json()
    assert Decimal(body["gap"]) == Decimal(body["kept"]) - Decimal(body["balances_change"])
    assert Decimal(body["kept"]) == Decimal(body["money_in"]) - Decimal(body["money_out"])
    names = [a["name"] for a in body["accounts"]]
    assert names, body
    keys = {c["key"] for c in body["causes"]}
    assert "accounts" in keys  # one statement: no balance at the start
    assert (
        client.get("/api/reconcile", params={"from": "2026-09-01", "to": "2026-08-01"}).status_code
        == 422
    )
