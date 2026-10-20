from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ingestion.storage import LocalStore
from app.models import Account
from tests.fixtures import statements as s

PDF = "application/pdf"


def _post(client: TestClient, *files: tuple[str, bytes]):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/statements",
        files=[("files", (name, data, PDF)) for name, data in files],
        headers={"X-MS-CLIENT-PRINCIPAL-NAME": "Lauren@Example.com"},
    )


def test_upload_detects_every_sample_and_stores_the_file(
    client: TestClient, store: LocalStore
) -> None:
    resp = _post(
        client,
        ("bofa.pdf", s.bofa()),
        ("capitalone.pdf", s.capitalone()),
        ("pichincha.pdf", s.pichincha()),
        ("produbanco.pdf", s.produbanco()),
        ("unknown.pdf", s.unknown()),
    )
    assert resp.status_code == 200
    results = {r["file_name"]: r for r in resp.json()}
    assert all(r["outcome"] == "stored" for r in results.values())

    bofa = results["bofa.pdf"]["statement"]
    assert bofa["source_label"] == "Bank of America" and bofa["status"] == "detected"
    assert sorted(a["last4"] for a in bofa["accounts"]) == ["1862", "8872"]
    assert (bofa["period_start"], bofa["period_end"]) == ("2026-08-22", "2026-09-22")
    assert bofa["uploaded_by"] == "lauren@example.com" and bofa["account_match"] == "last4"
    assert results["capitalone.pdf"]["statement"]["accounts"][0]["name"] == "Capital One Venture"
    assert results["unknown.pdf"]["statement"]["status"] == "unknown_format"
    assert "Bank of America: BofA" in results["bofa.pdf"]["message"]

    stored = sorted(p.parent.name for p in Path(store.root).rglob("*.pdf"))
    assert stored == ["bofa", "capitalone", "pichincha", "produbanco", "unknown"]
    listed = client.get("/api/statements").json()
    assert len(listed) == 5
    file = client.get(f"/api/statements/{bofa['statement_file_id']}/file")
    assert file.status_code == 200 and file.content == s.bofa()
    assert file.headers["content-type"] == PDF


def test_reupload_is_rejected_as_duplicate(client: TestClient) -> None:
    first = _post(client, ("a.pdf", s.capitalone()))
    assert first.json()[0]["outcome"] == "stored"
    again = _post(client, ("renamed.pdf", s.capitalone()), ("b.pdf", s.capitalone()))
    assert [r["outcome"] for r in again.json()] == ["duplicate", "duplicate"]
    assert "Already uploaded as a.pdf" in again.json()[0]["message"]
    assert len(client.get("/api/statements").json()) == 1


def test_bad_files_are_rejected(client: TestClient) -> None:
    resp = _post(
        client,
        ("notes.pdf", b"hello"),
        ("locked.pdf", s.encrypted()),
        ("empty.pdf", b""),
    )
    outcomes = {r["file_name"]: r for r in resp.json()}
    assert {r["outcome"] for r in outcomes.values()} == {"rejected"}
    assert "password-protected" in outcomes["locked.pdf"]["message"]
    assert "empty" in outcomes["empty.pdf"]["message"]
    assert client.get("/api/statements").json() == []


def test_too_many_or_too_large(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    many = [(f"{i}.pdf", b"x") for i in range(51)]
    assert _post(client, *many).status_code == 422
    from app.ingestion import upload

    monkeypatch.setattr(upload, "MAX_BYTES", 10)
    assert _post(client, ("big.pdf", s.unknown())).json()[0]["message"] == "Larger than 25 MB."


def test_account_resolution_fallbacks(client: TestClient, db: Session) -> None:
    # Replacement Pichincha card (new digits): the bank's only account.
    pich = _post(client, ("p.pdf", s.pichincha("546600XXXXXX6331"))).json()[0]["statement"]
    assert pich["accounts"][0]["name"] == "Pichincha Mastercard Black"
    assert pich["account_match"] == "by_bank" and pich["last4_found"] == ["6331"]

    # Lauren's Produbanco: the bank's one account without last four digits on file.
    lau = _post(client, ("l.pdf", s.produbanco("88888885555"))).json()[0]["statement"]
    assert lau["accounts"][0]["name"] == "Produbanco Lauren"

    # Diners: two cards without digits, so Hernan chooses.
    din = _post(client, ("d.pdf", s.diners())).json()[0]
    assert din["statement"]["status"] == "needs_account" and "which account" in din["message"]
    acct = db.scalar(select(Account).where(Account.name == "Diners Club Lauren"))
    assert acct is not None
    fixed = client.patch(
        f"/api/statements/{din['statement']['statement_file_id']}",
        json={"account_ids": [acct.account_id]},
    ).json()
    assert fixed["status"] == "detected" and fixed["account_match"] == "manual"
    assert fixed["accounts"][0]["name"] == "Diners Club Lauren"

    # Ambiguous Produbanco once both accounts have digits that don't match.
    db.execute(update(Account).where(Account.name == "Produbanco Lauren").values(last4="5555"))
    db.commit()
    other = _post(client, ("o.pdf", s.produbanco("77777770000"))).json()[0]["statement"]
    assert other["status"] == "needs_account" and other["accounts"] == []


def test_patch_and_file_errors(client: TestClient) -> None:
    assert client.patch("/api/statements/999", json={"account_ids": [1]}).status_code == 404
    assert client.get("/api/statements/999/file").status_code == 404
    sid = _post(client, ("c.pdf", s.capitalone())).json()[0]["statement"]["statement_file_id"]
    assert client.patch(f"/api/statements/{sid}", json={"account_ids": [9999]}).status_code == 404
    assert client.patch(f"/api/statements/{sid}", json={"account_ids": []}).status_code == 422


def test_local_store_refuses_paths_outside_its_folder(store: LocalStore) -> None:
    with pytest.raises(ValueError):
        store.put("../escape.pdf", b"x")
