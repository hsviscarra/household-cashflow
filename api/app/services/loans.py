"""Loan amortization tables (F14, ADR-014).

A lender's amortization table (BIESS "Tabla de amortización") lists every installment: number,
period (YYYY-MM), principal, interest, insurance and other charges, the total, the balance after
it and its state (CANCELADO = paid, POR VENCER = still to come, VENCIDO = overdue). Reading it:
- each row is "N YYYY-MM <amounts...> TOTAL BALANCE STATE"; the first two amounts are principal
  and interest, the last two the total and the balance, and whatever is between (insurance, late
  interest, collection charges; blank columns are simply missing) is "other";
- before anything is saved: installments run 1..N without gaps, each row's amounts add up to its
  total, and each balance is the previous one less that row's principal (the first from the
  approved amount), all to the cent.
Only the numbers are kept: no ID number, name or loan number, and not the file.

The loan's balance on the balance sheet then comes from the table: one snapshot per paid
installment, the balance after it dated the 1st of its month (the lender already marks it paid),
replaced when a newer table is uploaded.
"""

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import pdfplumber
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    BalanceSnapshot,
    Holding,
    LoadLog,
    LoanInstallment,
    RecurringEntry,
    RecurringTemplate,
    Transaction,
)
from app.services import recurring

SOURCE = "amortization"
CENT = Decimal("0.01")
ZERO = Decimal(0)
PAID = {"CANCELADO", "PAGADO"}
STATES = ("CANCELADO", "PAGADO", "POR VENCER", "VENCIDO")
ROW = re.compile(
    r"^(?P<n>\d{1,4})\s+(?P<y>\d{4})-(?P<m>\d{2})\s+(?P<amounts>[\d.,\s]+?)\s+"
    r"(?P<state>CANCELADO|PAGADO|POR VENCER|VENCIDO)\s*$"
)
APPROVED = re.compile(r"MONTO APROBADO\s*:\s*([\d.,]+)")
TERM = re.compile(r"PLAZO\s*:\s*(\d+)\s*Meses", re.IGNORECASE)
MATCH_TOLERANCE = Decimal("1.00")
LENDER_WORDS = ("IESS", "BIESS")


class LoanError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Row:
    number: int
    period: date
    principal: Decimal
    interest: Decimal
    other: Decimal
    total: Decimal
    balance_after: Decimal
    state: str

    @property
    def paid(self) -> bool:
        return self.state in PAID


@dataclass
class Table:
    rows: list[Row]
    approved: Decimal | None
    term: int | None
    problems: list[str] = field(default_factory=list)


def _money(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(text) from exc


def read_table(data: bytes) -> Table:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception as exc:  # pdfplumber raises several kinds for a broken file
        raise LoanError("This file could not be read as a PDF.") from exc
    if "TABLA DE AMORTIZ" not in text.upper():
        raise LoanError("This isn't an amortization table (no “Tabla de amortización” heading).")
    approved = APPROVED.search(text)
    term = TERM.search(text)
    rows: list[Row] = []
    problems: list[str] = []
    for line in text.splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        amounts = [_money(x) for x in m["amounts"].split()]
        n = int(m["n"])
        if len(amounts) < 4:
            problems.append(f"Installment {n}: too few amounts to read.")
            continue
        principal, interest, *middle, total, balance = amounts
        if principal + interest + sum(middle, ZERO) != total:
            problems.append(f"Installment {n}: its amounts don't add up to its total {total}.")
        rows.append(
            Row(
                n,
                date(int(m["y"]), int(m["m"]), 1),
                principal,
                interest,
                total - principal - interest,
                total,
                balance,
                m["state"],
            )
        )
    if not rows:
        raise LoanError("No installments were found in the table.")
    rows.sort(key=lambda r: r.number)
    for i, r in enumerate(rows, start=1):
        if r.number != i:
            problems.append(f"Installment {i} is missing.")
            break
    previous = _money(approved[1]) if approved else None
    for r in rows:
        if previous is not None and abs(previous - r.principal - r.balance_after) > CENT:
            problems.append(
                f"Installment {r.number}: the balance {r.balance_after} isn't the previous "
                f"{previous} less the principal {r.principal}."
            )
            break
        previous = r.balance_after
    return Table(
        rows, _money(approved[1]) if approved else None, int(term[1]) if term else None, problems
    )


def _loan(db: Session, holding_id: int) -> Holding:
    h = db.get(Holding, holding_id)
    if h is None:
        raise LoanError(f"Item {holding_id} not found.", 404)
    if h.holding_class != "loan":
        raise LoanError(f"{h.name} isn't a loan.")
    return h


def _month_end(month: date) -> date:
    return recurring.add_months(month, 1) - timedelta(days=1)


@dataclass
class ImportResult:
    installments: int
    paid: int
    due: int
    balance: Decimal | None
    as_of: date | None


def import_table(db: Session, holding_id: int, data: bytes, user: str) -> ImportResult:
    h = _loan(db, holding_id)
    table = read_table(data)
    if table.problems:
        raise LoanError("The table doesn't check out: " + " ".join(table.problems[:3]))
    db.execute(delete(LoanInstallment).where(LoanInstallment.holding_id == holding_id))
    db.execute(
        delete(BalanceSnapshot).where(
            BalanceSnapshot.holding_id == holding_id, BalanceSnapshot.source == SOURCE
        )
    )
    db.add_all(
        LoanInstallment(
            holding_id=holding_id,
            number=r.number,
            period=r.period,
            principal=r.principal,
            interest=r.interest,
            other=r.other,
            total=r.total,
            balance_after=r.balance_after,
            status="paid" if r.paid else "due",
        )
        for r in table.rows
    )
    paid = [r for r in table.rows if r.paid]
    db.add_all(
        BalanceSnapshot(
            as_of=r.period,
            name=h.name[:100],
            kind="liability",
            amount=r.balance_after,
            source=SOURCE,
            holding_id=holding_id,
            notes=f"Installment {r.number} paid",
        )
        for r in paid
    )
    db.add(
        LoadLog(
            source=SOURCE,
            file_sha256=hashlib.sha256(data).hexdigest(),
            loaded_by=user,
            rows_loaded=len(table.rows),
            summary=json.dumps(
                {"file_name": f"{h.name} amortization table", "installments": len(table.rows)}
            ),
        )
    )
    db.commit()
    last = paid[-1] if paid else None
    return ImportResult(
        len(table.rows),
        len(paid),
        len(table.rows) - len(paid),
        last.balance_after if last else None,
        last.period if last else None,
    )


# ---------------------------------------------------------------- reading
def installments(db: Session, holding_id: int) -> list[LoanInstallment]:
    return list(
        db.scalars(
            select(LoanInstallment)
            .where(LoanInstallment.holding_id == holding_id)
            .order_by(LoanInstallment.number)
        )
    )


@dataclass
class Schedule:
    installments: int
    paid: int
    left: int
    next_period: date | None
    next_total: Decimal | None
    payoff: date | None
    balance: Decimal | None
    interest_this_year: Decimal
    interest_left: Decimal
    other_left: Decimal


def schedule(db: Session, holding_id: int, today: date) -> Schedule | None:
    rows = installments(db, holding_id)
    if not rows:
        return None
    paid = [r for r in rows if r.status == "paid"]
    due = [r for r in rows if r.status == "due"]
    return Schedule(
        len(rows),
        len(paid),
        len(due),
        due[0].period if due else None,
        due[0].total if due else None,
        rows[-1].period,
        paid[-1].balance_after if paid else None,
        sum((r.interest for r in paid if r.period.year == today.year), ZERO),
        sum((r.interest for r in due), ZERO),
        sum((r.other for r in due), ZERO),
    )


def due_by_month(db: Session) -> dict[int, dict[date, Decimal]]:
    """For each recurring item that pays a loan with a table: the amount due per month."""
    out: dict[int, dict[date, Decimal]] = {}
    for h in db.scalars(
        select(Holding).where(
            Holding.holding_class == "loan", Holding.recurring_template_id.is_not(None)
        )
    ):
        rows = installments(db, h.holding_id)
        if rows and h.recurring_template_id is not None:
            out[h.recurring_template_id] = {r.period: r.total for r in rows if r.status == "due"}
    return out


@dataclass
class Payment:
    number: int
    period: date
    total: Decimal
    status: str
    line_id: int | None = None
    line_date: date | None = None
    line_amount: Decimal | None = None
    line_description: str | None = None
    account_name: str | None = None


def payments(
    db: Session, holding_id: int, today: date, back: int = 12, ahead: int = 3
) -> list[Payment]:
    """The last installments and the next ones, each with the bank line that paid it: a
    statement or manual line of about the same amount (within 1.00) around its month (from the
    15th of the month before to the 15th of the month after), paid through the loan's recurring
    item, in its category, or with IESS/BIESS in the description. Each line pays one
    installment."""
    h = _loan(db, holding_id)
    rows = installments(db, holding_id)
    start = recurring.add_months(recurring.first(today), -back)
    paid = [r for r in rows if r.status == "paid" and r.period >= start]
    due = [r for r in rows if r.status == "due"][:ahead]
    template = (
        db.get(RecurringTemplate, h.recurring_template_id) if h.recurring_template_id else None
    )
    via_template: set[int] = set()
    if template is not None:
        via_template = set(
            db.scalars(
                select(Transaction.transaction_id)
                .join(RecurringEntry, RecurringEntry.entry_id == Transaction.recurring_entry_id)
                .where(RecurringEntry.template_id == template.template_id)
            )
        )
    lines = list(
        db.scalars(
            select(Transaction).where(
                Transaction.source != "excel_history",
                Transaction.amount < 0,
                Transaction.txn_date >= start - timedelta(days=31),
            )
        )
    )
    names = {a.account_id: a.name for a in db.scalars(select(Account))}
    used: set[int] = set()
    out = []
    for r in [*paid, *due]:
        p = Payment(r.number, r.period, r.total, r.status)
        lo = r.period - timedelta(days=16)
        hi = _month_end(r.period) + timedelta(days=15)

        def fits(t: Transaction, r: LoanInstallment = r, lo: date = lo, hi: date = hi) -> bool:
            if t.transaction_id in used or not (lo <= t.txn_date <= hi):
                return False
            if abs(-t.amount - r.total) > MATCH_TOLERANCE:
                return False
            text = t.description_raw.upper()
            return (
                t.transaction_id in via_template
                or (template is not None and t.category_id == template.category_id)
                or any(w in text for w in LENDER_WORDS)
            )

        found = [t for t in lines if fits(t)]
        if found:
            best = min(
                found, key=lambda t: (abs((t.txn_date - r.period).days - 7), t.transaction_id)
            )
            used.add(best.transaction_id)
            p.line_id, p.line_date, p.line_amount = best.transaction_id, best.txn_date, best.amount
            p.line_description = best.description_raw
            p.account_name = names.get(best.account_id or -1)
        out.append(p)
    return out
