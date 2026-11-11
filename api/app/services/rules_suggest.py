"""Rules from your own choices (ADR-042): a merchant categorized the same way at least twice by
hand, with no rule matching it yet, is offered as a rule. From ADR-079 the second choice saves
the rule by itself (`learn`), when the description names someone or something."""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FROM_BANKS, MerchantRule, Transaction
from app.services import rules as rule_engine
from app.services.classify import merchant_key

MIN_TIMES = 2
BY_HAND = ("manual", "suggestion")
OWNERS = ("Hernan", "Lauren", "Joint")  # whom a rule may set (ck_merchant_rule_set_person)


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
            Transaction.source.in_(FROM_BANKS),
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


@dataclass
class Learned:
    rule_id: int
    pattern: str
    lines: int  # other lines the new rule categorized


def learn(db: Session, t: Transaction, user: str) -> Learned | None:
    """After a category chosen by hand: when this merchant now has MIN_TIMES lines categorized by
    hand, all to one category, and no rule knows it, save the rule and apply it to the lines
    still waiting (ADR-079). Never for a bare transfer text ("TRANSFERENCIA INTERNET": it names
    no one), a merchant whose rule was deleted or turned off, or one categorized two ways."""
    from app.services import classify, todo  # todo and classify import this module's users

    key = merchant_key(t.description_raw or "")
    if t.category_id is None or len(key) < 3 or not todo.rule_ok(key):
        return None
    if db.scalar(select(MerchantRule.rule_id).where(MerchantRule.pattern == key).limit(1)):
        return None  # there was a rule once: a person removed it or turned it off
    rules = [
        rule_engine.Rule.of(r)
        for r in db.scalars(select(MerchantRule).where(MerchantRule.is_active))
    ]
    if rule_engine.first_match(rules, t.description_raw, t.amount):
        return None
    same = [
        x
        for x in db.scalars(
            select(Transaction).where(
                Transaction.source.in_(FROM_BANKS),
                Transaction.category_id.is_not(None),
                Transaction.category_source.in_(BY_HAND),
            )
        )
        if merchant_key(x.description_raw or "") == key
    ]
    if len(same) < MIN_TIMES or {x.category_id for x in same} != {t.category_id}:
        return None
    people = {x.person for x in same}
    rule = MerchantRule(
        pattern=key,
        match_type="contains",
        category_id=t.category_id,
        priority=classify.REVIEW_RULE_PRIORITY,
        set_person=who if len(people) == 1 and (who := next(iter(people))) in OWNERS else None,
    )
    db.add(rule)
    db.flush()
    lines = classify.apply_rule(db, rule, user + " (learned)")
    db.commit()
    return Learned(rule.rule_id, key, lines)
