"""Bills found in the statements (ADR-043): charges that repeat monthly, every three months or
yearly with a similar amount (the subscription finder, ADR-011) and that no recurring item covers
yet. Each comes with what a recurring item needs, so adding it is one click."""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RecurringTemplate, Transaction
from app.services import subscriptions

EVERY = {"monthly": 1, "quarterly": 3, "yearly": 12}
MIN_PATTERN = 3


@dataclass
class FoundBill:
    """A recurring charge found in the lines that no recurring item covers yet."""

    merchant: str
    every_months: int
    amount: Decimal  # the typical charge, positive
    category_id: int
    category_path: str | None
    account_id: int | None
    account_name: str | None
    person: str | None
    match_pattern: str | None  # text every charge's description holds
    due_day: int
    times: int
    last_date: date
    next_expected: date | None
    examples: list[str]


def pattern_of(descriptions: list[str]) -> str | None:
    """The merchant text every description holds: their common start, trimmed to whole words."""
    upper = [d.upper().strip() for d in descriptions]
    common = upper[0]
    for u in upper[1:]:
        n = next((i for i, (a, b) in enumerate(zip(common, u, strict=False)) if a != b), None)
        common = common[: min(len(common), len(u))] if n is None else common[:n]
    if common and not all(len(u) == len(common) or u[len(common)] == " " for u in upper):
        common = common.rsplit(" ", 1)[0] if " " in common else ""
    common = common.strip(" *-#")
    return common if len(common) >= MIN_PATTERN else None


def _covered(templates: list[RecurringTemplate], t: Transaction) -> bool:
    for tpl in templates:
        if tpl.category_id != t.category_id:
            continue
        if tpl.account_id is not None and tpl.account_id != t.account_id:
            continue
        pattern = (tpl.match_pattern or "").casefold()
        if pattern in t.description_raw.casefold():
            return True
    return False


IN_BATCH = 500  # ids per IN (...) list


def _charged(db: Session, ids: list[int]) -> dict[int, Transaction]:
    """The lines behind the steady charges, read together instead of one query each."""
    out: dict[int, Transaction] = {}
    for start in range(0, len(ids), IN_BATCH):
        for t in db.scalars(
            select(Transaction).where(Transaction.transaction_id.in_(ids[start : start + IN_BATCH]))
        ):
            out[t.transaction_id] = t
    return out


def find(db: Session, today: date | None = None) -> list[FoundBill]:
    """Subscriptions found in the lines that no recurring item covers yet: bills to add."""
    templates = list(db.scalars(select(RecurringTemplate).where(RecurringTemplate.is_active)))
    out = []
    subs = [s for s in subscriptions.find(db, today) if s.cadence in EVERY and s.active]
    by_id = _charged(db, [c.transaction_id for s in subs for c in s.charges])
    for sub in subs:
        rows = [by_id[c.transaction_id] for c in sub.charges if c.transaction_id in by_id]
        if any(t.recurring_entry_id is not None for t in rows):
            continue
        cats = [t.category_id for t in rows if t.category_id is not None]
        if not cats:
            continue  # categorize it first; a recurring item needs a category
        category_id = Counter(cats).most_common(1)[0][0]
        last = rows[-1]
        if _covered(templates, last):
            continue
        accounts = Counter(t.account_id for t in rows)
        people = {t.person for t in rows}
        out.append(
            FoundBill(
                merchant=sub.merchant,
                every_months=EVERY[sub.cadence],
                amount=sub.typical,
                category_id=category_id,
                category_path=sub.category_path,
                account_id=accounts.most_common(1)[0][0],
                account_name=sub.charges[-1].account_name,
                person=people.pop() if len(people) == 1 else None,
                match_pattern=pattern_of([t.description_raw for t in rows]),
                due_day=int(median(t.txn_date.day for t in rows)),
                times=len(rows),
                last_date=last.txn_date,
                next_expected=sub.next_expected,
                examples=[t.description_raw for t in rows[-3:]],
            )
        )
    out.sort(key=lambda b: (-b.amount / b.every_months, b.merchant))
    return out
