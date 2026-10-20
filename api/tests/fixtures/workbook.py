"""A small synthetic Cash Flow workbook with the same layout as the real one. No real data."""

import calendar
from datetime import datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook

MONTHS = list(calendar.month_name[1:])


def _sheet(wb: Workbook, title: str, headers: list[str], rows: dict[int, dict[str, Any]]) -> None:
    ws = wb.create_sheet(title)
    for i, h in enumerate(headers):
        ws.cell(1, 2 + i, h)
    for r, cells in rows.items():
        for col, value in cells.items():
            ws[f"{col}{r}"] = value


def build(*, extra_income_label: str | None = None, lauren_jan_2026: float = 3100) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    # 14 months: November 2019 to December 2020 (like the real 2021 sheet that spans years).
    _sheet(
        wb,
        "Cash Flow 2020",
        ["November", "December", *MONTHS],
        {
            2: {"A": "INCOME"},
            3: {"A": "Salaries"},
            4: {"A": "Lauren", "B": 1100, "D": 1250.5},
            5: {"A": "Hernan", "C": 600},
            6: {"A": "Total", "B": 1100, "C": 999, "D": 1250.5},
            7: {"A": "EXPENSES"},
            8: {"A": "Condo Fee", "B": 210, "D": 210},
            9: {"A": "Capital One", "C": 320},
            10: {"A": "TOTAL", "B": 210, "C": 320, "D": 210},
            12: {"A": "Available Income", "B": 890},
            14: {"A": "Health", "B": 45},  # second block: not imported
        },
    )

    rows_2025: dict[int, dict[str, Any]] = {
        2: {"A": "INCOME"},
        3: {"A": "Total"},
        4: {"A": "EXPENSES"},
        30: {"B": 31.4},  # unlabeled row that stands for Phone
        31: {"A": "TOTAL", "B": 31.4},
    }
    _sheet(wb, "Cash Flow 2025", [*MONTHS, "", "Enero"], rows_2025)

    income: dict[int, dict[str, Any]] = {
        2: {"A": "INCOME"},
        3: {"A": "Salaries"},
        4: {"A": "Lauren", "B": lauren_jan_2026, "H": 3200},
        5: {"A": "Hernan", "B": 4900.25, "H": 4900},
        6: {"A": "Others"},
        7: {"A": "Office Rent", "B": 500},
        9: {"A": "Total", "B": lauren_jan_2026 + 4900.25 + 500},
    }
    if extra_income_label:
        income[8] = {"A": extra_income_label, "B": 10}
    _sheet(
        wb,
        "Cash Flow 2026",
        MONTHS,
        {
            **income,
            10: {"A": "EXPENSES"},
            11: {"A": "Health Appointments"},
            12: {"A": "Hernan", "B": 60.1},
            13: {"A": "Others"},
            14: {"A": "Interactive Brokers", "B": 700, "H": 700},
            15: {"A": "Aliquota Ofi", "B": 75.35},
            16: {"A": "TOTAL", "B": "=SUM(B12:B14)"},
            18: {"A": "Available Income"},
            20: {"A": "Others", "C": 15},
            21: {"A": "TOTAL"},
            23: {"A": "SAVINGS / INVESTMENTS", "E": 900},
            24: {"A": "Stock Market", "E": 12000},
            26: {"A": "DEUDAS"},
            27: {"A": "Diners", "B": 0},
            28: {"A": "BIESS", "B": 30000.55},
            29: {"A": "TOTAL"},
            31: {"A": "Johana Pagos"},
            32: {"A": "1era quincena", "B": 200},
            33: {"A": "Total", "B": 200},
            35: {"A": "FIRST US TRANSFER PAYMENTS"},
            36: {"A": "Transferred to Lender A", "B": 5000},
            37: {"A": datetime(2026, 5, 5), "B": 900, "C": "Bank transfer"},
            38: {"A": "Remaining to pay Lender A", "B": 1500},
            39: {"A": "SECOND US TRANSFER"},
            40: {"A": "Remaining to pay Lender A", "B": 8000},
            41: {"A": "Total due payments", "B": 9500},
        },
    )
    wb.create_sheet("Expenses")  # other sheets are ignored

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


if __name__ == "__main__":
    import sys

    # uv run python -m tests.fixtures.workbook ../web/e2e/fixtures/cash-flow-sample.xlsx
    with open(sys.argv[1], "wb") as out:
        out.write(build())
