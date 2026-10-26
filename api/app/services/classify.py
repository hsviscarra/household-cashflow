"""Classification after loading (F9): the review queue of uncategorized lines grouped by merchant,
categorizing a group (optionally saving a rule that is then applied to every uncategorized line it
matches), editing one line, and splitting a line into parts. Every change to a loaded line is
written to audit.change_log with its old and new value.
"""

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import Exists, and_, exists, select
from sqlalchemy.orm import Session, aliased

from app.models import Account, Category, ChangeLog, MerchantRule, MerchantSuggestion, Transaction
from app.services import rules as rule_engine
from app.services import transfers

# Lower than the seeded merchant rules (10-30): a rule Hernan saves while reviewing is specific.
REVIEW_RULE_PRIORITY = 15


class ClassifyError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def merchant_key(description: str) -> str:
    """What groups lines of the same merchant: uppercase, reference numbers (4+ digits) and
    store numbers and confirmation codes dropped, so "MICROSOFT*123456 MSBILL" and
    "MICROSOFT*987654 MSBILL" are one, and so are two Zelle payments to the same person."""
    text = rule_engine.normalize(description)
    # Confirmation and payment codes ("CONF# AB12CD34E", "ID:PAYCO1234X"): letters and digits mixed.
    text = re.sub(r"\b(?:CONF#|ID:)\s*\S+", " ", text)
    text = re.sub(r"\b(?=[A-Z]*\d)(?=\d*[A-Z])[A-Z\d]{6,}\b", " ", text)
    text = re.sub(r"[#*]?\d{4,}", " ", text)
    text = re.sub(r"\s#?\d{1,3}\b", " ", text)
    return " ".join(text.split())[:200]


def type_for(category: Category, amount: Decimal) -> str:
    """The transaction type a category gives a line: money back on a spending category is a
    refund; transfers, income and savings follow the category's kind."""
    if category.kind in ("transfer", "income", "savings"):
        return category.kind
    return "refund" if amount > 0 else "expense"


def _log(
    db: Session, row: Transaction, column: str, old: object, new: object, reason: str, user: str
) -> None:
    if old == new:
        return
    db.add(
        ChangeLog(
            table_name="core.transaction",
            row_id=row.transaction_id,
            column_name=column,
            old_value=None if old is None else str(old)[:400],
            new_value=None if new is None else str(new)[:400],
            reason=reason[:200],
            changed_by=user,
        )
    )


def set_category(
    db: Session,
    row: Transaction,
    category: Category,
    source: str,
    reason: str,
    user: str,
    rule_id: int | None = None,
) -> None:
    new_type = type_for(category, row.amount)
    _log(db, row, "category_id", row.category_id, category.category_id, reason, user)
    _log(db, row, "type", row.type, new_type, reason, user)
    row.category_id = category.category_id
    row.type = new_type
    row.is_fixed = category.is_fixed
    row.category_source = source
    row.rule_id = rule_id


# ---------------- review queue ----------------
@dataclass
class ReviewLine:
    transaction_id: int
    txn_date: date
    amount: Decimal
    description: str
    account_name: str | None
    person: str | None


@dataclass
class ReviewGroup:
    merchant_key: str
    lines: list[ReviewLine] = field(default_factory=list)
    suggestion: MerchantSuggestion | None = None

    @property
    def total(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), Decimal(0))


def _has_parts() -> Exists:
    part = aliased(Transaction)
    return exists().where(part.parent_transaction_id == Transaction.transaction_id)


def uncategorized(db: Session, month: date | None = None) -> list[Transaction]:
    q = select(Transaction).where(
        Transaction.category_id.is_(None),
        Transaction.source == "statement",
        ~_has_parts(),
    )
    if month:
        q = q.where(Transaction.cash_month == month.replace(day=1))
    return list(db.scalars(q.order_by(Transaction.txn_date, Transaction.transaction_id)))


def review_groups(db: Session, month: date | None = None) -> list[ReviewGroup]:
    accounts = {a.account_id: a.name for a in db.scalars(select(Account))}
    groups: dict[str, ReviewGroup] = {}
    for t in uncategorized(db, month):
        key = merchant_key(t.description_raw)
        group = groups.setdefault(key, ReviewGroup(key))
        group.lines.append(
            ReviewLine(
                t.transaction_id,
                t.txn_date,
                t.amount,
                t.description_raw,
                accounts.get(t.account_id) if t.account_id else None,
                t.person,
            )
        )
    if groups:
        found = db.scalars(
            select(MerchantSuggestion).where(MerchantSuggestion.merchant_key.in_(list(groups)))
        )
        for s in found:
            groups[s.merchant_key].suggestion = s
    # Biggest money first: that is where a wrong category costs the most.
    return sorted(groups.values(), key=lambda g: (-abs(g.total), g.merchant_key))


@dataclass
class Resolved:
    categorized: int
    rule_id: int | None
    also_by_rule: int


def resolve(
    db: Session,
    key: str,
    category_id: int,
    user: str,
    *,
    transaction_ids: list[int] | None = None,
    save_rule: bool = False,
    pattern: str | None = None,
    match_type: str = "contains",
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    from_suggestion: bool = False,
) -> Resolved:
    """Categorize a merchant's uncategorized lines; with save_rule, also save a rule and apply it
    to every other uncategorized line it matches (any month)."""
    category = db.get(Category, category_id)
    if category is None:
        raise ClassifyError(f"Category {category_id} not found.", 404)
    rows = [t for t in uncategorized(db) if merchant_key(t.description_raw) == key]
    if transaction_ids is not None:
        rows = [t for t in rows if t.transaction_id in set(transaction_ids)]
    if not rows:
        raise ClassifyError("Those lines are already categorized or no longer exist.", 409)

    rule: MerchantRule | None = None
    if save_rule:
        text = (pattern or key).strip()
        error = rule_engine.validate_pattern(text, match_type)
        if error:
            raise ClassifyError(error)
        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            raise ClassifyError("The lowest amount must not be above the highest.")
        rule = MerchantRule(
            pattern=text,
            match_type=match_type,
            category_id=category.category_id,
            priority=REVIEW_RULE_PRIORITY,
            amount_min=amount_min,
            amount_max=amount_max,
        )
        db.add(rule)
        db.flush()

    source = "suggestion" if from_suggestion else "manual"
    reason = "Review: accepted Claude's suggestion" if from_suggestion else "Review: chosen"
    for t in rows:
        set_category(db, t, category, source, reason, user, rule.rule_id if rule else None)

    also = 0
    if rule is not None:
        also = apply_rule(db, rule, user, skip={t.transaction_id for t in rows})
    db.query(MerchantSuggestion).filter(MerchantSuggestion.merchant_key == key).delete()
    db.commit()
    if category.kind == "transfer":
        transfers.match(db, user)  # a line just called a transfer may have its other side loaded
    return Resolved(len(rows), rule.rule_id if rule else None, also)


def apply_rule(db: Session, rule: MerchantRule, user: str, skip: set[int] | None = None) -> int:
    """Categorize every uncategorized statement line the rule matches. Lines Hernan already
    categorized are never touched."""
    category = db.get(Category, rule.category_id)
    assert category is not None
    engine_rule = rule_engine.Rule.of(rule)
    count = 0
    for t in uncategorized(db):
        if skip and t.transaction_id in skip:
            continue
        if rule_engine.matches(engine_rule, t.description_raw, t.amount):
            set_category(db, t, category, "rule", f"Rule {rule.rule_id}", user, rule.rule_id)
            count += 1
    return count


# ---------------- one line ----------------
def edit(
    db: Session,
    row: Transaction,
    user: str,
    *,
    category_id: int | None = None,
    notes: str | None = None,
    person: str | None = None,
    fields: set[str],
) -> None:
    if "category_id" in fields:
        if category_id is None:
            raise ClassifyError("Choose a category.")
        category = db.get(Category, category_id)
        if category is None:
            raise ClassifyError(f"Category {category_id} not found.", 404)
        set_category(db, row, category, "manual", "Edited", user)
        if row.transfer_group_id is not None and category.kind != "transfer":
            transfers.unlink(db, row.transfer_group_id, user)  # no longer a transfer
    if "notes" in fields:
        _log(db, row, "notes", row.notes, notes, "Edited", user)
        row.notes = notes
    if "person" in fields:
        _log(db, row, "person", row.person, person, "Edited", user)
        row.person = person
    db.commit()
    if row.type == "transfer" and row.transfer_group_id is None:
        transfers.match(db, user)


# ---------------- splits ----------------
@dataclass
class Part:
    amount: Decimal
    category_id: int
    notes: str | None = None


def parts_of(db: Session, row: Transaction) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(Transaction.parent_transaction_id == row.transaction_id)
            .order_by(Transaction.transaction_id)
        )
    )


def split(db: Session, row: Transaction, parts: list[Part], user: str) -> list[Transaction]:
    """Replace a line with parts that add up to it exactly (same sign); the line itself stays as
    loaded and stops counting, its parts count instead."""
    if row.parent_transaction_id is not None:
        raise ClassifyError("A part can't be split again; split the original line.")
    if len(parts) < 2:
        raise ClassifyError("A split needs at least two parts.")
    if any(p.amount == 0 or (p.amount > 0) != (row.amount > 0) for p in parts):
        raise ClassifyError("Every part must be non-zero and in the same direction as the line.")
    total = sum((p.amount for p in parts), Decimal(0))
    if total != row.amount:
        raise ClassifyError(f"The parts add up to {total}, not {row.amount}.")
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    missing = [p.category_id for p in parts if p.category_id not in cats]
    if missing:
        raise ClassifyError(f"Category {missing[0]} not found.", 404)

    unsplit(db, row, user, commit=False)
    made = []
    for i, p in enumerate(parts, start=1):
        cat = cats[p.category_id]
        key = hashlib.sha256(f"{row.natural_key}|part|{i}".encode()).hexdigest()
        part = Transaction(
            natural_key=key,
            account_id=row.account_id,
            statement_file_id=row.statement_file_id,
            raw_line_id=row.raw_line_id,
            import_batch_id=row.import_batch_id,
            txn_date=row.txn_date,
            post_date=row.post_date,
            cash_month=row.cash_month,
            amount=p.amount,
            description_raw=row.description_raw,
            merchant=row.merchant,
            pay_reference=row.pay_reference,
            notes=p.notes,
            type=type_for(cat, p.amount),
            category_id=cat.category_id,
            category_source="split",
            person=row.person,
            country=row.country,
            is_fixed=cat.is_fixed,
            source=row.source,
            status=row.status,
            parent_transaction_id=row.transaction_id,
        )
        db.add(part)
        made.append(part)
    db.flush()
    summary = "; ".join(f"{p.amount} → {cats[p.category_id].name}" for p in parts)
    _log(db, row, "split", None, summary, "Split", user)
    db.commit()
    return made


def unsplit(db: Session, row: Transaction, user: str, commit: bool = True) -> int:
    parts = parts_of(db, row)
    if parts:
        summary = "; ".join(f"{p.amount}" for p in parts)
        _log(db, row, "split", summary, None, "Split removed", user)
        for p in parts:
            db.delete(p)
        db.flush()
    if commit:
        db.commit()
    return len(parts)


def history(db: Session, row: Transaction) -> list[ChangeLog]:
    return list(
        db.scalars(
            select(ChangeLog)
            .where(
                and_(
                    ChangeLog.table_name == "core.transaction",
                    ChangeLog.row_id == row.transaction_id,
                )
            )
            .order_by(ChangeLog.change_id)
        )
    )


def part_counts(db: Session, ids: list[int]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    if ids:
        for (parent,) in db.execute(
            select(Transaction.parent_transaction_id).where(
                Transaction.parent_transaction_id.in_(ids)
            )
        ):
            if parent is not None:
                counts[parent] += 1
    return counts
