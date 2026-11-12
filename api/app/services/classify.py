"""Classification after loading (F9): the review queue of uncategorized lines grouped by merchant,
categorizing a group (optionally saving a rule that is then applied to every uncategorized line it
matches), editing one line, and splitting a line into parts. Every change to a loaded line is
written to audit.change_log with its old and new value.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import Exists, and_, exists, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    FROM_BANKS,
    Account,
    Category,
    ChangeLog,
    Counterparty,
    ImportBatch,
    MerchantRule,
    MerchantSuggestion,
    RawLine,
    StgTransaction,
    Transaction,
)
from app.services import rules as rule_engine
from app.services import transfers

# Lower than the seeded merchant rules (10-30): a rule Hernan saves while reviewing is specific.
REVIEW_RULE_PRIORITY = 15


class ClassifyError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def merchant_key(description: str) -> str:
    """What groups lines of the same merchant; the rule engine owns it (`rules.key`)."""
    return rule_engine.key(description)


def type_for(category: Category, amount: Decimal) -> str:
    """The transaction type a category gives a line: money back on a spending category is a
    refund; transfers, income and savings follow the category's kind; a debt category (a loan,
    a house being paid off) makes it a debt payment (ADR-054)."""
    if category.kind == "debt":
        return "debt_payment"
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
    transaction_id: int  # a loaded line; on a statement's page, the staged line (stg_id)
    txn_date: date
    amount: Decimal
    description: str
    account_name: str | None
    person: str | None
    account_id: int | None = None
    post_date: date | None = None
    statement_file_id: int | None = None  # where to open the statement (ADR-034)
    page: int | None = None


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
        Transaction.source.in_(FROM_BANKS),
        ~_has_parts(),
    )
    if month:
        q = q.where(Transaction.cash_month == month.replace(day=1))
    return list(db.scalars(q.order_by(Transaction.txn_date, Transaction.transaction_id)))


def review_groups(db: Session, month: date | None = None) -> list[ReviewGroup]:
    accounts = {a.account_id: a.name for a in db.scalars(select(Account))}
    groups: dict[str, ReviewGroup] = {}
    rows = uncategorized(db, month)
    pages = _pages(db, [t.raw_line_id for t in rows if t.raw_line_id])
    for t in rows:
        key = merchant_key(t.description_raw)
        group = groups.setdefault(key, ReviewGroup(key))
        file_id, page = pages.get(t.raw_line_id or 0, (t.statement_file_id, None))
        group.lines.append(
            ReviewLine(
                t.transaction_id,
                t.txn_date,
                t.amount,
                t.description_raw,
                accounts.get(t.account_id) if t.account_id else None,
                t.person,
                t.account_id,
                t.post_date,
                file_id,
                page,
            )
        )
    return _with_suggestions(db, groups)


def _pages(db: Session, raw_line_ids: list[int]) -> dict[int, tuple[int, int]]:
    """raw_line_id -> (statement file, page), in chunks (SQL Server allows ~2,100 parameters)."""
    out: dict[int, tuple[int, int]] = {}
    for i in range(0, len(raw_line_ids), 1000):
        chunk = raw_line_ids[i : i + 1000]
        q = select(RawLine.raw_line_id, RawLine.statement_file_id, RawLine.page).where(
            RawLine.raw_line_id.in_(chunk)
        )
        for rid, fid, page in db.execute(q):
            out[rid] = (fid, page)
    return out


def staged_uncategorized(db: Session, batch_id: int) -> list[StgTransaction]:
    """A statement's lines still waiting for a category (already-loaded duplicates aside)."""
    return list(
        db.scalars(
            select(StgTransaction)
            .where(
                StgTransaction.batch_id == batch_id,
                StgTransaction.category_id.is_(None),
                StgTransaction.is_duplicate == False,  # noqa: E712 (SQL Server needs = 0)
            )
            .order_by(StgTransaction.txn_date, StgTransaction.stg_id)
        )
    )


def batch_groups(db: Session, batch_id: int) -> list[ReviewGroup]:
    """The Review queue for one statement waiting for approval (F23): its uncategorized lines
    grouped by merchant, so they can be categorized before the statement is loaded."""
    accounts = {a.account_id: a.name for a in db.scalars(select(Account))}
    groups: dict[str, ReviewGroup] = {}
    staged = staged_uncategorized(db, batch_id)
    pages = _pages(db, [s.raw_line_id for s in staged])
    for s in staged:
        key = merchant_key(s.description_raw)
        groups.setdefault(key, ReviewGroup(key)).lines.append(
            ReviewLine(
                s.stg_id,
                s.txn_date,
                s.amount,
                s.description_raw,
                accounts.get(s.account_id),
                s.person,
                s.account_id,
                s.post_date,
                *pages.get(s.raw_line_id, (None, None)),
            )
        )
    return _with_suggestions(db, groups)


def _with_suggestions(db: Session, groups: dict[str, ReviewGroup]) -> list[ReviewGroup]:
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
    waiting_by_rule: int = 0  # lines in statements not approved yet


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

    rule = (
        _new_rule(db, key, category, pattern, match_type, amount_min, amount_max)
        if save_rule
        else None
    )

    source = "suggestion" if from_suggestion else "manual"
    reason = "Review: accepted Claude's suggestion" if from_suggestion else "Review: chosen"
    for t in rows:
        set_category(db, t, category, source, reason, user, rule.rule_id if rule else None)

    also = waiting = 0
    if rule is not None:
        also = apply_rule(db, rule, user, skip={t.transaction_id for t in rows})
        waiting = classify_waiting(db, rule=rule)
    db.query(MerchantSuggestion).filter(MerchantSuggestion.merchant_key == key).delete()
    db.commit()
    if category.kind == "transfer":
        transfers.match(db, user)  # a line just called a transfer may have its other side loaded
    return Resolved(len(rows), rule.rule_id if rule else None, also, waiting)


def _new_rule(
    db: Session,
    key: str,
    category: Category,
    pattern: str | None,
    match_type: str,
    amount_min: Decimal | None,
    amount_max: Decimal | None,
) -> MerchantRule:
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
    return rule


def resolve_staged(
    db: Session,
    batch_id: int,
    key: str,
    category_id: int,
    user: str,
    *,
    stg_ids: list[int] | None = None,
    save_rule: bool = False,
    pattern: str | None = None,
    match_type: str = "contains",
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    from_suggestion: bool = False,
) -> Resolved:
    """Categorize a merchant's lines in a statement waiting for approval (F23), all of them or
    only `stg_ids` (one merchant can mean two categories). With save_rule,
    the rule also reaches loaded lines and the other waiting statements, as in Review."""
    category = db.get(Category, category_id)
    if category is None:
        raise ClassifyError(f"Category {category_id} not found.", 404)
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ClassifyError(f"Import {batch_id} not found.", 404)
    if batch.status != "preview":
        raise ClassifyError(f"This statement is already {batch.status}.", 409)
    rows = [s for s in staged_uncategorized(db, batch_id) if merchant_key(s.description_raw) == key]
    if stg_ids is not None:
        rows = [s for s in rows if s.stg_id in set(stg_ids)]
    if not rows:
        raise ClassifyError("Those lines are already categorized or no longer exist.", 409)
    rule = (
        _new_rule(db, key, category, pattern, match_type, amount_min, amount_max)
        if save_rule
        else None
    )
    for s in rows:
        s.category_id = category.category_id
        s.type = type_for(category, s.amount)
        s.rule_id = rule.rule_id if rule else None
        s.category_source = "suggestion" if from_suggestion else "manual"
    also = waiting = 0
    if rule is not None:
        db.flush()
        also = apply_rule(db, rule, user)
        waiting = classify_waiting(db, rule=rule)
    db.query(MerchantSuggestion).filter(MerchantSuggestion.merchant_key == key).delete()
    db.commit()
    return Resolved(len(rows), rule.rule_id if rule else None, also, waiting)


@dataclass
class Accepted:
    merchants: int
    lines: int
    also_by_rule: int


def accept_suggestions(
    db: Session,
    user: str,
    *,
    min_confidence: Decimal,
    month: date | None = None,
    batch_id: int | None = None,
) -> Accepted:
    """Accept every Claude suggestion at or above `min_confidence`, saving a rule for each (one
    click on Review or a statement's page). Lower ones stay for a person to look at."""
    groups = batch_groups(db, batch_id) if batch_id is not None else review_groups(db, month)
    picked = [
        (g.merchant_key, g.suggestion.category_id)
        for g in groups
        if g.suggestion is not None and g.suggestion.confidence >= min_confidence
    ]
    done = Accepted(0, 0, 0)
    for key, category_id in picked:
        try:
            if batch_id is not None:
                r = resolve_staged(
                    db, batch_id, key, category_id, user, save_rule=True, from_suggestion=True
                )
            else:
                r = resolve(db, key, category_id, user, save_rule=True, from_suggestion=True)
        except ClassifyError:
            db.rollback()  # an earlier rule may have categorized it already; go on
            continue
        done.merchants += 1
        done.lines += r.categorized
        done.also_by_rule += r.also_by_rule + r.waiting_by_rule
    return done


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
            reason = f"Rule {rule.rule_id}"
            set_category(db, t, category, "rule", reason, user, rule.rule_id)
            if rule.set_person and t.person != rule.set_person:
                _log(db, t, "person", t.person, rule.set_person, reason, user)
                t.person = rule.set_person
            if rule.merchant_name:
                t.merchant = engine_rule.merchant()
            count += 1
    return count


def apply_rules(db: Session, user: str) -> int:
    """Categorize every uncategorized loaded line that an active rule matches, the first rule by
    priority winning as in an import. The daily check-in runs it, so a rule that starts to match
    (ADR-085) or was saved while a line was elsewhere still reaches it. The caller commits."""
    rows = {r.rule_id: r for r in db.scalars(select(MerchantRule).where(MerchantRule.is_active))}
    rules = [rule_engine.Rule.of(r) for r in rows.values()]
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    count = 0
    for t in uncategorized(db):
        hit = rule_engine.first_match(rules, t.description_raw, t.amount)
        if hit is None or hit.category_id not in cats:
            continue
        reason = f"Rule {hit.rule_id}"
        set_category(db, t, cats[hit.category_id], "rule", reason, user, hit.rule_id)
        if hit.set_person and t.person != hit.set_person:
            _log(db, t, "person", t.person, hit.set_person, reason, user)
            t.person = hit.set_person
        if hit.merchant_name:
            t.merchant = hit.merchant()
        count += 1
    return count


# ---------------- statements waiting for approval ----------------
def classify_waiting(
    db: Session, *, batch_id: int | None = None, rule: MerchantRule | None = None
) -> int:
    """Apply rules to the uncategorized lines of statements still waiting for approval (all of
    them, or one batch), so a rule saved after a statement was read still reaches it. With `rule`,
    only that rule. Lines a rule or the statement's section already categorized are left alone.
    Returns how many lines were categorized; the caller commits."""
    q = (
        select(StgTransaction, Account)
        .join(ImportBatch, ImportBatch.batch_id == StgTransaction.batch_id)
        .join(Account, Account.account_id == StgTransaction.account_id)
        .where(ImportBatch.status == "preview", StgTransaction.category_id.is_(None))
    )
    if batch_id is not None:
        q = q.where(StgTransaction.batch_id == batch_id)
    waiting = db.execute(q).all()
    if not waiting:
        return 0
    rows = [rule] if rule is not None else list(db.scalars(select(MerchantRule)))
    rules = [rule_engine.Rule.of(r) for r in rows]
    by_id = {c.category_id: c for c in db.scalars(select(Category))}
    count = 0
    for s, account in waiting:
        hit = rule_engine.first_match(rules, s.description_raw, s.amount)
        if hit is None:
            continue
        s.type = rule_type(by_id[hit.category_id].kind, account, s.amount)
        s.category_id, s.rule_id = hit.category_id, hit.rule_id
        s.merchant = hit.merchant()
        if hit.set_person:
            s.person = hit.set_person
        count += 1
    db.flush()
    return count


def rule_type(kind: str, account: Account, amount: Decimal) -> str:
    # Money in on a card is a refund; on a bank account it is income until a rule says otherwise.
    money_in = "refund" if account.kind == "credit_card" else "income"
    default = money_in if amount > 0 else "expense"
    kinds = {"transfer": "transfer", "income": "income", "savings": "savings"}
    return "debt_payment" if kind == "debt" else kinds.get(kind, default)


# ---------------- one line ----------------
def edit(
    db: Session,
    row: Transaction,
    user: str,
    *,
    category_id: int | None = None,
    notes: str | None = None,
    person: str | None = None,
    counterparty_id: int | None = None,
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
    if "counterparty_id" in fields:
        if counterparty_id is not None and db.get(Counterparty, counterparty_id) is None:
            raise ClassifyError(f"Person {counterparty_id} not found.", 404)
        _log(db, row, "counterparty_id", row.counterparty_id, counterparty_id, "Edited", user)
        row.counterparty_id = counterparty_id
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
