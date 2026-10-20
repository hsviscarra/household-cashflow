"""Optional check against Hernan's real workbook, run locally only:

    REAL_WORKBOOK="/path/to/Cash Flow.xlsx" uv run pytest tests/unit/test_real_workbook.py -q

The workbook never enters git; without the variable this test is skipped.
"""

import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.excel_history import parse_workbook

PATH = os.environ.get("REAL_WORKBOOK")
pytestmark = pytest.mark.skipif(not PATH, reason="REAL_WORKBOOK not set")


def test_real_workbook_loads_and_ties_to_the_cent(client: TestClient) -> None:
    assert PATH
    data = Path(PATH).read_bytes()
    parsed = parse_workbook(data)
    assert parsed.unmapped == []
    unexplained = [c for c in parsed.checks if not c.explained]
    assert all(c.typed_total for c in unexplained), [c.month for c in unexplained]

    resp = client.post(
        "/api/history/excel/load",
        files={"file": ("Cash Flow.xlsx", data, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text

    expected: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for r in parsed.actual_rows:
        assert r.cell.month is not None
        expected[r.cell.month.isoformat()][0 if r.mapping.type == "income" else 1] += r.cell.value
    monthly = client.get("/api/cashflow/monthly").json()
    assert len(monthly) == len(expected)
    for m in monthly:
        inc, out = expected[m["cash_month"]]
        outflows = sum(Decimal(m[k]) for k in ("expenses", "savings", "debt_payments"))
        assert Decimal(m["income"]).quantize(Decimal("0.01")) == inc.quantize(Decimal("0.01"))
        assert outflows.quantize(Decimal("0.01")) == out.quantize(Decimal("0.01"))
