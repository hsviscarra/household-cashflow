"""Everything known about one line, to decide what it was (ADR-074).

The open line on Transactions shows, beside its category: other lines with the same amount, the
other side of a transfer or its candidates, the invoice that paid it or invoices that could have,
the rule that set its category, and whether it is unusual on a card kept for one purpose
(Juliana's school card).
"""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased, selectinload

from app.models import Account, AppSetting, Category, Invoice, MerchantRule, Transaction
from app.services import invoice_category
from app.services import rules as rule_engine

NEAR_DAYS = 7  # a transfer's other side, an invoice: within a week
INVOICE_DAYS = 5
SAME_AMOUNT = 6
PURPOSE_KEY = "card-purpose:"


@dataclass
class Other:
    """Another line that may be this one's pair or its repeat."""

    transaction_id: int
    txn_date: date
    amount: Decimal
    description: str
    account_name: str | None
    category_path: str | None
    type: str


@dataclass
class InvoiceBrief:
    """An invoice near a line, in short, and whether it is linked to it."""

    invoice_id: int
    issuer_name: str
    issue_date: date
    total: Decimal
    products: list[str]
    linked: bool  # paid by this line


@dataclass
class RuleBrief:
    """The rule that categorized a line."""

    rule_id: int
    pattern: str
    match_type: str
    category_path: str | None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None


@dataclass
class Purpose:
    """What an account is for, and what is usual and unusual on it."""

    account_name: str
    for_whom: str
    usual: list[str]
    unusual: bool  # this line doesn't look like the card's purpose


@dataclass
class Context:
    """Everything known about a line that helps to categorize it."""

    transaction_id: int
    category_source: str | None
    rule: RuleBrief | None
    same_amount: list[Other] = field(default_factory=list)
    transfer_side: list[Other] = field(default_factory=list)  # paired lines
    transfer_candidates: list[Other] = field(default_factory=list)
    invoices: list[InvoiceBrief] = field(default_factory=list)
    purpose: Purpose | None = None


def _paths(db: Session) -> dict[int, str]:
    parent = aliased(Category)
    rows = db.execute(
        select(Category.category_id, Category.name, parent.name).outerjoin(
            parent, parent.category_id == Category.parent_id
        )
    )
    return {cid: f"{g} / {c}" if g else c for cid, c, g in rows}


def purposes(db: Session) -> dict[int, dict[str, object]]:
    """Cards kept for one purpose: account id → {"for": who, "usual": [words in descriptions]}."""
    out: dict[int, dict[str, object]] = {}
    for s in db.scalars(select(AppSetting).where(AppSetting.setting_key.like(f"{PURPOSE_KEY}%"))):
        try:
            out[int(s.setting_key[len(PURPOSE_KEY) :])] = json.loads(s.setting_value)
        except (ValueError, TypeError):
            continue
    return out


def is_usual(t: Transaction, purpose: dict[str, object]) -> bool:
    """A line fits the card's purpose: a fee or interest, a payment to the card, or a merchant
    whose words the purpose lists."""
    if t.type in ("fee_interest", "transfer", "debt_payment") or t.amount > 0:
        return True
    text = " ".join((t.description_raw or "").upper().split())
    words = purpose.get("usual")
    if not isinstance(words, list):
        return False
    return any(w.upper() in text for w in words if isinstance(w, str))


def unusual_lines(db: Session, since: date) -> list[tuple[Transaction, str]]:
    """Lines on a purpose card that don't look like its purpose, since a day: (line, for whom)."""
    out = []
    for aid, p in purposes(db).items():
        q = select(Transaction).where(
            Transaction.account_id == aid,
            Transaction.txn_date >= since,
            Transaction.parent_transaction_id.is_(None),
        )
        for t in db.scalars(q.order_by(Transaction.txn_date.desc())):
            if not is_usual(t, p):
                out.append((t, str(p.get("for") or "")))
    return out


def build(db: Session, t: Transaction) -> Context:
    """What the app knows about a line: same-amount lines, invoices near it, its transfer side
    and what its card is usually used for."""
    paths = _paths(db)
    accounts = {a.account_id: a.name for a in db.scalars(select(Account))}

    def other(x: Transaction) -> Other:
        return Other(
            x.transaction_id,
            x.txn_date,
            x.amount,
            x.description_raw,
            accounts.get(x.account_id or 0),
            paths.get(x.category_id or 0),
            x.type,
        )

    ctx = Context(t.transaction_id, t.category_source, None)

    # The rule that sets lines like it.
    active = [rule_engine.Rule.of(r) for r in db.scalars(select(MerchantRule))]
    hit = rule_engine.first_match(active, t.description_raw or "", t.amount)
    if hit is not None:
        ctx.rule = RuleBrief(
            hit.rule_id,
            hit.pattern,
            hit.match_type,
            paths.get(hit.category_id),
            hit.amount_min,
            hit.amount_max,
        )

    # Other lines of exactly this amount: a monthly bill shows its category.
    same = db.scalars(
        select(Transaction)
        .where(
            Transaction.amount == t.amount,
            Transaction.transaction_id != t.transaction_id,
            Transaction.source != "excel_history",
        )
        .order_by(Transaction.txn_date.desc())
        .limit(SAME_AMOUNT)
    )
    ctx.same_amount = [other(x) for x in same]

    # A transfer's other side, or what could be.
    if t.transfer_group_id is not None:
        ctx.transfer_side = [
            other(x)
            for x in db.scalars(
                select(Transaction).where(
                    Transaction.transfer_group_id == t.transfer_group_id,
                    Transaction.transaction_id != t.transaction_id,
                )
            )
        ]
    if not ctx.transfer_side and t.type == "transfer":
        near = db.scalars(
            select(Transaction)
            .where(
                Transaction.amount == -t.amount,
                Transaction.account_id != t.account_id,
                Transaction.txn_date >= t.txn_date - timedelta(days=NEAR_DAYS),
                Transaction.txn_date <= t.txn_date + timedelta(days=NEAR_DAYS),
            )
            .limit(5)
        )
        ctx.transfer_candidates = [other(x) for x in near]

    # The invoice that paid it, or invoices of the same amount around its day.
    q = (
        select(Invoice)
        .options(selectinload(Invoice.lines))
        .where(
            (Invoice.transaction_id == t.transaction_id)
            | (
                Invoice.transaction_id.is_(None)
                & (Invoice.total == -t.amount)
                & (Invoice.issue_date >= t.txn_date - timedelta(days=INVOICE_DAYS))
                & (Invoice.issue_date <= t.txn_date + timedelta(days=INVOICE_DAYS))
            )
        )
        .limit(5)
    )
    for inv in db.scalars(q):
        top = sorted(inv.lines, key=lambda ln: -ln.total)[:5]
        ctx.invoices.append(
            InvoiceBrief(
                inv.invoice_id,
                inv.issuer_name,
                inv.issue_date,
                inv.total,
                [ln.description for ln in top],
                inv.transaction_id == t.transaction_id,
            )
        )

    p = purposes(db).get(t.account_id or 0)
    if p is not None:
        ctx.purpose = Purpose(
            accounts.get(t.account_id or 0, ""),
            str(p.get("for") or ""),
            [str(w) for w in u] if isinstance(u := p.get("usual"), list) else [],
            not is_usual(t, p),
        )
    return ctx


def link_invoice(db: Session, t: Transaction, invoice_id: int) -> Invoice:
    """Say which invoice this line paid (a person's choice; the invoice's products may then set
    the line's category, ADR-066)."""
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise LookupError("No such invoice.")
    for old in db.scalars(select(Invoice).where(Invoice.transaction_id == t.transaction_id)):
        old.transaction_id = None
    inv.transaction_id = t.transaction_id
    db.commit()
    invoice_category.apply(db, since=inv.issue_date)
    return inv
