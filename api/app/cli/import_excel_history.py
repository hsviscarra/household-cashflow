"""Preview or load the Cash Flow workbook from a terminal, against DATABASE_URL.

    uv run python -m app.cli.import_excel_history path/to/Cash\\ Flow.xlsx            # preview
    uv run python -m app.cli.import_excel_history path/to/Cash\\ Flow.xlsx --load     # load

The web app does the same from the Import page; this is for local runs and the bulk load.
"""

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import get_engine
from app.services import history_load
from app.services.excel_history import parse_workbook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--load", action="store_true", help="load after the preview")
    args = parser.parse_args(argv)

    data = args.workbook.read_bytes()
    parsed = parse_workbook(data)
    sha = history_load.sha256(data)
    with Session(get_engine()) as db:
        p = history_load.preview(db, parsed, args.workbook.name, sha)
        print(
            f"{p.first_month} to {p.last_month}: {p.months} months, {p.actual_rows} rows, "
            f"{p.plan_rows} plan rows, {len(p.snapshots)} balance snapshots"
        )
        for y in p.years:
            print(
                f"  {y.year}: income {y.income:,.2f}  outflows {y.outflows:,.2f}"
                f"  ({y.months} months)"
            )
        print(f"Months where the workbook TOTAL differs from its rows: {len(p.mismatches)}")
        for m in p.mismatches:
            why = "typed-in total" if m.typed_total else ", ".join(m.left_out)
            flag = "" if m.explained else "  <-- not explained"
            print(f"  {m.month:%Y-%m}: {why}{flag}")
        if p.unmapped:
            print("Unmapped rows:", ", ".join(sorted({u.label for u in p.unmapped})))
            return 1
        if not args.load:
            return 0
        user = getpass.getuser()
        try:
            result = history_load.load(db, parsed, args.workbook.name, sha, user)
        except history_load.HistoryError as exc:
            print(f"Not loaded: {exc}", file=sys.stderr)
            return 1
        print(f"Loaded: {result.model_dump()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
