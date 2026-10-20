from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BalanceSnapshot, Budget, ExcelCell, LoadLog, Transaction
from tests.fixtures.workbook import build

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upload(client: TestClient, action: str, data: bytes, name: str = "Cash Flow.xlsx"):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/history/excel/{action}",
        files={"file": (name, data, XLSX)},
        headers={"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"},
    )


def test_preview_summarizes_without_writing(client: TestClient, db: Session) -> None:
    resp = _upload(client, "preview", build())
    assert resp.status_code == 200
    p = resp.json()
    assert (p["first_month"], p["last_month"]) == ("2019-11-01", "2026-01-01")
    assert p["plan_months"] == ["2026-07-01"]
    assert p["already_loaded"] is False and p["unmapped"] == []
    y2026 = next(y for y in p["years"] if y["year"] == 2026)
    assert Decimal(y2026["income"]) == Decimal("8500.25")
    assert Decimal(y2026["outflows"]) == Decimal("835.45")
    jan = next(m for m in p["mismatches"] if m["month"] == "2026-01-01")
    assert jan["left_out"] == ["Aliquota Ofi 75.35"]
    card = next(m for m in p["mapping"] if m["label"] == "Capital One")
    assert (card["type"], card["category"], card["months"]) == (
        "debt_payment",
        "Transfers/Card Payment",
        1,
    )
    assert not [m for m in p["mapping"] if m["review"]]  # the fixture holds no guessed rows
    assert len(p["snapshots"]) == 5 and p["side_cells"] > 0
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_load_then_read_cashflow(client: TestClient, db: Session) -> None:
    resp = _upload(client, "load", build())
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["transactions"] == 13 and out["budget_rows"] == 3 and out["snapshots"] == 5
    assert out["replaced_transactions"] == 0

    log = db.scalars(select(LoadLog)).one()
    assert log.loaded_by == "hernan@example.com" and log.rows_loaded == 13
    assert db.scalar(select(func.count()).select_from(ExcelCell)) == out["raw_cells"]

    monthly = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    jan = monthly["2026-01-01"]
    assert Decimal(jan["income"]) == Decimal("8500.25")
    assert Decimal(jan["expenses"]) == Decimal("135.45")
    assert Decimal(jan["savings"]) == Decimal("700")
    assert Decimal(jan["net"]) == Decimal("7664.80")
    dec = monthly["2019-12-01"]
    assert Decimal(dec["debt_payments"]) == Decimal("320") and Decimal(dec["net"]) == Decimal("280")
    assert Decimal(monthly["2026-01-01"]["cumulative_net"]) == Decimal("9843.90")
    filtered = client.get("/api/cashflow/monthly", params={"from": "2026-01-01"}).json()
    assert [m["cash_month"] for m in filtered] == ["2026-01-01"]
    assert (
        client.get("/api/cashflow/monthly", params={"to": "2019-11-01"}).json()[0]["cash_month"]
        == "2019-11-01"
    )

    cats = client.get("/api/cashflow/categories", params={"year": 2026}).json()
    health = next(c for c in cats if c["group_name"] == "Health")
    assert health["category_name"] == "Doctors" and Decimal(health["amount"]) == Decimal("60.1")
    assert health["group_color"] == "#00897B"

    plan = client.get("/api/cashflow/plan").json()
    assert [p["month"] for p in plan] == ["2026-07-01"]
    assert Decimal(plan[0]["income"]) == Decimal("8100")
    assert Decimal(plan[0]["outflows"]) == Decimal("700")


def test_same_file_twice_is_refused_and_a_new_version_replaces(
    client: TestClient, db: Session
) -> None:
    # Build once: openpyxl stamps the save time, so two builds can differ by a second.
    book = build()
    assert _upload(client, "load", book).status_code == 200
    again = _upload(client, "load", book)
    assert again.status_code == 409
    assert _upload(client, "preview", book).json()["already_loaded"] is True

    newer = _upload(client, "load", build(lauren_jan_2026=3500))
    assert newer.status_code == 200
    assert newer.json()["replaced_transactions"] == 13
    assert db.scalar(select(func.count()).select_from(Transaction)) == 13
    assert db.scalar(select(func.count()).select_from(Budget)) == 3
    assert db.scalar(select(func.count()).select_from(BalanceSnapshot)) == 5
    jan = client.get("/api/cashflow/monthly", params={"from": "2026-01-01"}).json()[0]
    assert Decimal(jan["income"]) == Decimal("8900.25")


def test_refuses_unmapped_rows_and_non_workbooks(client: TestClient, db: Session) -> None:
    resp = _upload(client, "load", build(extra_income_label="Lottery"))
    assert resp.status_code == 422 and "Lottery" in resp.json()["detail"]
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    assert _upload(client, "preview", b"not excel", "notes.txt").status_code == 422
    assert _upload(client, "preview", b"not excel", "fake.xlsx").status_code == 422


def test_empty_database_reads(client: TestClient) -> None:
    assert client.get("/api/cashflow/monthly").json() == []
    assert client.get("/api/cashflow/categories", params={"year": 2026}).json() == []
    assert client.get("/api/cashflow/plan").json() == []
    assert client.get("/api/cashflow/categories", params={"year": 1}).status_code == 422
