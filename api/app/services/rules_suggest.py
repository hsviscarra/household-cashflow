"""Rules suggested from your own choices (ADR-042): a merchant categorized the same way at least
twice by hand, with no rule matching it yet, is offered as a rule."""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MerchantRule, Transaction
from app.services import rules as rule_engine
from app.services.classify import merchant_key

MIN_TIMES = 2
BY_HAND = ("manual", "suggestion")


@dataclass
class Suggestion:
    pattern: str
    category_id: int
    times: int
    example: str
    person: str | None  # set when every line was the same person's


def suggestions(db: Session, limit: int = 20) -> list[Suggestion]:
    rules = [
        rule_engine.Rule.of(r)
        for r in db.scalars(select(MerchantRule).where(MerchantRule.is_active))
    ]
    seen: dict[str, list[Transaction]] = defaultdict(list)
    rows = db.scalars(
        select(Transaction).where(
            Transaction.source == "statement",
            Transaction.category_id.is_not(None),
            Transaction.category_source.in_(BY_HAND),
        )
    )
    for t in rows:
        key = merchant_key(t.description_raw)
        if len(key) >= 3:
            seen[key].append(t)
    out = []
    for key, lines in seen.items():
        cats = {t.category_id for t in lines}
        if len(lines) < MIN_TIMES or len(cats) != 1:
            continue
        if any(rule_engine.first_match(rules, t.description_raw, t.amount) for t in lines):
            continue
        people = {t.person for t in lines}
        out.append(
            Suggestion(
                key,
                lines[0].category_id or 0,
                len(lines),
                lines[-1].description_raw,
                people.pop() if len(people) == 1 else None,
            )
        )
    out.sort(key=lambda s: (-s.times, s.pattern))
    return out[:limit]
