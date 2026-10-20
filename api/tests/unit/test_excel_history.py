from datetime import date
from decimal import Decimal

from app.services.excel_history import _left_out, parse_workbook
from app.services.excel_mapping import lookup, norm
from tests.fixtures.workbook import build


def test_months_count_back_from_december_of_the_sheet_year() -> None:
    parsed = parse_workbook(build())
    lauren = sorted(
        (c.month, c.value)
        for c in parsed.cells
        if c.sheet == "Cash Flow 2020" and c.label == "Lauren"
    )
    assert lauren == [(date(2019, 11, 1), Decimal("1100")), (date(2020, 1, 1), Decimal("1250.5"))]
    hernan = next(c for c in parsed.cells if c.sheet == "Cash Flow 2020" and c.label == "Hernan")
    assert hernan.month == date(2019, 12, 1)


def test_second_block_and_spanish_columns_are_skipped() -> None:
    parsed = parse_workbook(build())
    assert not [c for c in parsed.cells if c.label == "Health"]
    assert all(c.month is None or c.month.year >= 2019 for c in parsed.cells)
    assert {c.sheet for c in parsed.cells} == {"Cash Flow 2020", "Cash Flow 2025", "Cash Flow 2026"}


def test_mapping_uses_group_headers_and_unlabeled_rows() -> None:
    parsed = parse_workbook(build())
    by_label = {(r.cell.block, r.cell.label): r for r in parsed.rows}
    assert by_label[("income", "Hernan")].mapping.category == "Salary/Hernan"
    assert by_label[("expense", "Hernan")].mapping.category == "Health/Doctors"
    assert by_label[("expense", "Phone")].mapping.category == "Utilities/Phone/Internet"
    assert by_label[("expense", "Interactive Brokers")].mapping.type == "savings"
    assert by_label[("expense", "Capital One")].mapping.type == "debt_payment"


def test_2026_after_june_is_plan() -> None:
    parsed = parse_workbook(build())
    plan = {(r.cell.label, r.cell.month) for r in parsed.plan_rows}
    assert plan == {
        ("Lauren", date(2026, 7, 1)),
        ("Hernan", date(2026, 7, 1)),
        ("Interactive Brokers", date(2026, 7, 1)),
    }
    assert all(r.cell.month and r.cell.month <= date(2026, 6, 1) for r in parsed.actual_rows)


def test_signed_amounts_and_stable_keys() -> None:
    a = parse_workbook(build())
    b = parse_workbook(build())
    ib = next(r for r in a.actual_rows if r.cell.label == "Interactive Brokers")
    rent = next(r for r in a.actual_rows if r.cell.label == "Office Rent")
    assert ib.signed_amount == Decimal("-700") and rent.signed_amount == Decimal("500")
    assert [r.natural_key for r in a.rows] == [r.natural_key for r in b.rows]
    assert len({r.natural_key for r in a.rows}) == len(a.rows)


def test_checks_report_typed_totals_and_rows_left_out() -> None:
    checks = {c.month: c for c in parse_workbook(build()).checks}
    assert checks[date(2019, 11, 1)].matches
    dec = checks[date(2019, 12, 1)]
    assert not dec.matches and dec.typed_total and not dec.explained
    assert dec.income_rows == Decimal("600") and dec.income_workbook == Decimal("999")
    jan = checks[date(2026, 1, 1)]
    assert jan.left_out == ["Aliquota Ofi 75.35"]
    assert jan.left_out_total == Decimal("75.35")
    assert date(2026, 7, 1) not in checks


def test_side_tables_and_snapshots() -> None:
    parsed = parse_workbook(build())
    side = {c.label for c in parsed.cells if c.block.startswith("side:")}
    assert "Others" not in side and "Total due payments" not in side
    assert {"Stock Market", "Diners", "BIESS", "1era quincena", "2026-05-05"} <= side
    snaps = {(s.name, s.kind, s.as_of, s.amount) for s in parsed.snapshots}
    assert ("BIESS", "liability", date(2026, 1, 31), Decimal("30000.55")) in snaps
    assert ("Diners", "liability", date(2026, 1, 31), Decimal("0")) in snaps
    assert ("Stock Market", "asset", date(2026, 4, 30), Decimal("12000")) in snaps
    names = sorted(s.name for s in parsed.snapshots if s.name.startswith("Remaining"))
    assert names == ["Remaining to pay Lender A", "Remaining to pay Lender A (2)"]


def test_unmapped_rows_are_reported() -> None:
    parsed = parse_workbook(build(extra_income_label="Lottery"))
    assert [(c.label, c.value) for c in parsed.unmapped] == [("Lottery", Decimal("10"))]


def test_left_out_and_lookup_helpers() -> None:
    assert _left_out("=SUM(B13:B27)", [12, 13, 27, 30], 11, 40) == [12, 30]
    assert _left_out("=sum(c4:c6)", [4, 7], 2, 9) == [7]
    assert _left_out("=B10-B32", [4], 2, 9) is None
    assert _left_out(1234.5, [4], 2, 9) is None
    assert norm("  Killa   Guardería ") == "killa guarderia"
    assert lookup("expense", None, "Killa Guardería") == lookup("expense", None, "killa gaudaria")
    assert lookup("income", None, "Unknown") is None
