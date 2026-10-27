"""Guards against SQL that SQLite accepts but SQL Server rejects."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def test_no_boolean_is_comparisons() -> None:
    # column.is_(True) renders "IS 1", which T-SQL rejects; use the column itself or ~column.
    hits = [
        f"{path.relative_to(APP.parent)}:{n}"
        for path in APP.rglob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if re.search(r"\.is_(?:not)?\((?:True|False)\)", line)
    ]
    assert hits == []
