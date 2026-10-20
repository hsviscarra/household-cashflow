"""Optional checks against real statements, run locally only (files never enter git):

REAL_CAPITALONE="/path/to/statement.pdf" uv run pytest tests/unit/test_real_statements.py
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

CAPITALONE = os.environ.get("REAL_CAPITALONE")


@pytest.mark.skipif(not CAPITALONE, reason="REAL_CAPITALONE not set")
def test_real_capital_one_ties_out_and_loads(client: TestClient) -> None:
    assert CAPITALONE
    data = Path(CAPITALONE).read_bytes()
    up = client.post("/api/statements", files=[("files", ("co.pdf", data, "application/pdf"))])
    st = up.json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"], [c for c in b["checks"] if not c["ok"]]
    purchases = -sum(
        Decimal(ln["amount"]) for ln in b["lines"] if ln["type"] in ("expense", "refund")
    )
    print(f"\n{b['new_lines']} lines, purchases {purchases}, uncategorized {b['uncategorized']}")
    for ln in b["lines"]:
        if ln["category_path"] is None:
            print("  needs a category:", ln["description"], ln["amount"])
    ok = client.post(f"/api/batches/{b['batch_id']}/approve").json()
    assert ok["loaded"] == b["new_lines"]
