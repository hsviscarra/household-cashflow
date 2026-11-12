"""Income tax for the year, projected (ADR-088): what each person will owe, how much more in
invoices would still lower it, and what to set aside for the payment.

An estimate, not a return and not tax advice. It follows the SRI's arithmetic for a resident
person in the general regime:

    taxable = income of the year + withheld by the employer - exempt income - deductions
    tax     = the SRI's table for the year, applied to taxable
    due     = tax - rebate for personal expenses (18% of the deductible invoices, ADR-036)
    to pay  = due - withheld

Income is what the bank lines say: lines in the person's own category under Salary, by the day
they arrived (tax counts income when received, not the month it pays for, ADR-084). The months
still to come count the typical month. An employee's deposits are net of IESS and of the
employer's withholding, so IESS is already out and the withholding is added back; the décimos
are exempt and are entered as exempt income. Whoever is paid from abroad has nothing withheld
and pays everything in the return. Those three figures (withheld, exempt, deductions) can't be
read from a bank line: a person enters them, and until then they are zero and the page says so.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models import AppSetting, Category, Transaction
from app.services import gastos, payday, sources

log = logging.getLogger(__name__)

ZERO = Decimal(0)
CENT = Decimal("0.01")
HUNDRED = Decimal(100)

# SRI, Resolución NAC-DGERCGC25-00000043 (Dec 29 2025): personas naturales, ejercicio 2026.
# (from, up to, tax on the lower bound, % on the excess); None = no upper bound.
TABLES: dict[int, list[tuple[int, int | None, int, int]]] = {
    2026: [
        (0, 12208, 0, 0),
        (12208, 15549, 0, 5),
        (15549, 20188, 167, 10),
        (20188, 26700, 631, 12),
        (26700, 35136, 1412, 15),
        (35136, 46575, 2678, 20),
        (46575, 62005, 4965, 25),
        (62005, 82679, 8823, 30),
        (82679, 109956, 15025, 35),
        (109956, None, 24572, 37),
    ]
}
REGIMES = ("employee", "foreign", "independent")
# How each of them is taxed (Hernan, Nov 12 2026); a saved profile overrides it.
DEFAULT_REGIME = {"Hernan": "foreign", "Lauren": "employee"}
PROFILE_KEY = "tax-profile:"  # + year:person -> the four profile fields as JSON
TYPICAL_MONTHS = 3  # complete months whose median is "a typical month" of income
PAY_MONTH, PAY_DAY = 3, 15  # the return is paid in March of the next year, by RUC digit
DECEMBER = 12
WORKBOOK = "excel_history"  # core.transaction.source of the Cash Flow workbook's rows


class TaxError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Profile:
    regime: str
    withheld: Decimal = ZERO  # by the employer over the whole year
    exempt: Decimal = ZERO  # income that isn't taxed (décimos)
    deductions: Decimal = ZERO  # IESS paid on one's own, costs of the activity


@dataclass
class PersonTax:
    person: str
    year: int
    profile: Profile
    received: Decimal  # income in the bank so far this year
    typical_month: Decimal
    projected_income: Decimal  # received + the months to come
    taxable: Decimal
    tax: Decimal
    expenses: Decimal  # deductible invoices so far (before VAT), inside the cap
    cap: Decimal | None
    rebate: Decimal  # applied: never more than the tax
    room: Decimal  # more invoices that would still count, up to the cap
    more_rebate: Decimal  # what filling the room would still take off
    due: Decimal  # tax - rebate
    to_pay: Decimal  # due - withheld; negative = in the person's favour
    pay_on: date
    months_left: int
    set_aside: Decimal  # per month from now to the payment
    notes: list[str] = field(default_factory=list)


def tax_on(taxable: Decimal, year: int) -> Decimal:
    """The year's table applied to a taxable base."""
    table = TABLES.get(year)
    if table is None:
        raise TaxError(f"The SRI's income tax table for {year} isn't in the app yet.", 404)
    for low, high, base, pct in table:
        if high is None or taxable <= high:
            over = max(taxable - low, ZERO)
            return (Decimal(base) + over * Decimal(pct) / HUNDRED).quantize(CENT)
    raise AssertionError("the last row of a tax table has no upper bound")


def _key(person: str, year: int) -> str:
    return f"{PROFILE_KEY}{year}:{person}"


def profile(db: Session, person: str, year: int) -> Profile:
    row = db.get(AppSetting, _key(person, year))
    default = Profile(DEFAULT_REGIME.get(person, "employee"))
    if row is None:
        return default
    try:
        saved = json.loads(row.setting_value)
        return Profile(
            saved["regime"] if saved["regime"] in REGIMES else default.regime,
            Decimal(saved["withheld"]),
            Decimal(saved["exempt"]),
            Decimal(saved["deductions"]),
        )
    except (ValueError, KeyError, TypeError, ArithmeticError):
        log.warning("Tax projection: unreadable profile for %s %s", person, year)
        return default


def set_profile(db: Session, person: str, year: int, p: Profile, user: str) -> Profile:
    if person not in gastos.PEOPLE:
        raise TaxError(f"Person must be one of {', '.join(gastos.PEOPLE)}.")
    if p.regime not in REGIMES:
        raise TaxError(f"Regime must be one of {', '.join(REGIMES)}.")
    if min(p.withheld, p.exempt, p.deductions) < 0:
        raise TaxError("Amounts can't be negative.")
    value = json.dumps(
        {
            "regime": p.regime,
            "withheld": str(p.withheld),
            "exempt": str(p.exempt),
            "deductions": str(p.deductions),
        }
    )
    row = db.get(AppSetting, _key(person, year))
    if row is None:
        db.add(AppSetting(setting_key=_key(person, year), setting_value=value, updated_by=user))
    else:
        row.setting_value, row.updated_by = value, user
    db.commit()
    return p


def _by_month(db: Session, person: str, year: int) -> dict[int, Decimal]:
    """Income received in each month of the year: lines in the person's category under Salary,
    by the day they arrived. A month the workbook still counts for (ADR-018) takes the
    workbook's row instead, so nothing is counted twice."""
    group = aliased(Category)
    cats = select(Category.category_id).join(group, group.category_id == Category.parent_id)
    cats = cats.where(
        group.name == payday.SALARY_GROUP, group.parent_id.is_(None), Category.name == person
    )
    start, end = date(year, 1, 1), date(year + 1, 1, 1)
    rows = db.execute(
        select(
            Transaction.txn_date, Transaction.cash_month, Transaction.amount, Transaction.source
        ).where(
            Transaction.category_id.in_(cats),
            Transaction.amount > 0,
            Transaction.txn_date >= start,
            Transaction.txn_date < end,
        )
    )
    since = sources.statements_from(db)
    workbook: dict[int, Decimal] = {}
    banks: dict[int, Decimal] = {}
    for day, cash_month, amount, source in rows:
        if source == WORKBOOK:
            workbook[cash_month.month] = workbook.get(cash_month.month, ZERO) + amount
        else:
            banks[day.month] = banks.get(day.month, ZERO) + amount
    out: dict[int, Decimal] = {}
    for m in sorted({*workbook, *banks}):
        from_workbook = m in workbook and (since is None or date(year, m, 1) < since)
        value = workbook[m] if from_workbook else banks.get(m, ZERO)
        if value:
            out[m] = value
    return out


def _income(by_month: dict[int, Decimal], year: int, today: date) -> tuple[Decimal, Decimal]:
    """(a typical month, the year's income projected): months already over count what arrived;
    this month and the ones to come count the typical month, or what arrived if that is more."""
    if today.year > year:
        return ZERO, sum(by_month.values(), ZERO)
    current = today.month if today.year == year else 0
    done = [by_month[m] for m in sorted(by_month) if m < current]
    typical = Decimal(str(median(done[-TYPICAL_MONTHS:]))) if done else ZERO
    total = sum((v for m, v in by_month.items() if m < current), ZERO)
    for m in range(max(current, 1), DECEMBER + 1):
        total += max(by_month.get(m, ZERO), typical)
    return typical.quantize(CENT), total.quantize(CENT)


def _months_left(today: date, pay_on: date) -> int:
    """Months from this one to the payment's, at least one."""
    return max((pay_on.year - today.year) * 12 + pay_on.month - today.month, 1)


def _notes(p: Profile, typical: Decimal) -> list[str]:
    notes = []
    if typical == 0:
        notes.append("No complete month of income yet: the months to come count as zero.")
    if p.regime == "employee":
        if p.withheld == 0:
            notes.append(
                "Nothing entered as withheld: the tax is worked out on the deposits alone, and "
                "what the employer already withheld isn't taken off. Enter the year's withholding "
                "from the payslips."
            )
        if p.exempt == 0:
            notes.append("The décimos are exempt: enter them as exempt income if they were paid.")
    else:
        notes.append("Nothing is withheld on this income: all of it is paid with the return.")
    return notes


def person_tax(db: Session, person: str, year: int, today: date | None = None) -> PersonTax:
    today = today or date.today()
    p = profile(db, person, year)
    by_month = _by_month(db, person, year)
    typical, projected = _income(by_month, year, today)
    taxable = max(projected + p.withheld - p.exempt - p.deductions, ZERO).quantize(CENT)
    tax = tax_on(taxable, year)
    g = next(x for x in gastos.summary(db, year).people if x.person == person)
    rebate = min(g.rebate, tax)
    room = max(g.cap - g.total, ZERO) if g.cap is not None else ZERO
    more = min((room * gastos.RATE).quantize(CENT), tax - rebate)
    due = tax - rebate
    to_pay = due - p.withheld
    pay_on = date(year + 1, PAY_MONTH, PAY_DAY)
    left = _months_left(today, pay_on)
    return PersonTax(
        person=person,
        year=year,
        profile=p,
        received=sum(by_month.values(), ZERO).quantize(CENT),
        typical_month=typical,
        projected_income=projected,
        taxable=taxable,
        tax=tax,
        expenses=g.deductible,
        cap=g.cap,
        rebate=rebate,
        room=room,
        more_rebate=more,
        due=due,
        to_pay=to_pay,
        pay_on=pay_on,
        months_left=left,
        set_aside=(max(to_pay, ZERO) / left).quantize(CENT),
        notes=_notes(p, typical),
    )


def projection(db: Session, year: int, today: date | None = None) -> list[PersonTax]:
    return [person_tax(db, person, year, today) for person in gastos.PEOPLE]


def payments(db: Session, today: date, end: date) -> list[tuple[date, str, Decimal]]:
    """What the forecast should show: each person's payment that falls between today and `end`
    (day, name, amount to pay). Years without a table are skipped."""
    out = []
    for year in {today.year - 1, today.year}:
        if year not in TABLES:
            continue
        for t in projection(db, year, today):
            if t.to_pay > 0 and today <= t.pay_on <= end:
                out.append((t.pay_on, f"Income tax {year}, {t.person} (estimate)", t.to_pay))
    return sorted(out)
