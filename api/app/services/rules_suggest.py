"""Rules from your own choices (ADR-042): a merchant categorized the same way at least twice by
hand, with no rule matching it yet, is offered as a rule. From ADR-079 the second choice saves
the rule by itself (`learn`), when the description names someone or something."""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from app.models import FROM_BANKS, MerchantRule, Transaction
from app.services import classify
from app.services import rules as rule_engine

MIN_TIMES = 2
MIN_KEY = 3  # characters: a shorter key says too little to be a rule
IN_BATCH = 500  # keys per IN (...) list
BY_HAND = ("manual", "suggestion")
OWNERS = ("Hernan", "Lauren", "Joint")  # whom a rule may set (ck_merchant_rule_set_person)


@dataclass
class Suggestion:
    """A rule worth making: a pattern categorized the same way several times."""

    pattern: str
    category_id: int
    times: int
    example: str
    person: str | None  # set when every line was the same person's


def _by_hand() -> ColumnElement[bool]:
    """Lines from a bank whose category a person chose (by hand, or accepting a suggestion)."""
    return and_(
        Transaction.source.in_(FROM_BANKS),
        Transaction.category_id.is_not(None),
        Transaction.category_source.in_(BY_HAND),
    )


def suggestions(db: Session, limit: int = 20) -> list[Suggestion]:
    """Merchants categorized by hand MIN_TIMES or more, always the same way, that no active rule
    matches. The database groups by the stored merchant key (ADR-086); only the lines of the
    merchants that qualify are read."""
    keys = [
        k
        for (k,) in db.execute(
            select(Transaction.merchant_key)
            .where(
                _by_hand(), func.char_length(func.coalesce(Transaction.merchant_key, "")) >= MIN_KEY
            )
            .group_by(Transaction.merchant_key)
            .having(
                func.count() >= MIN_TIMES,
                func.count(func.distinct(Transaction.category_id)) == 1,
            )
        )
    ]
    if not keys:
        return []
    rules = [
        rule_engine.Rule.of(r)
        for r in db.scalars(select(MerchantRule).where(MerchantRule.is_active))
    ]
    seen: dict[str, list[Transaction]] = defaultdict(list)
    for start in range(0, len(keys), IN_BATCH):
        rows = db.scalars(
            select(Transaction)
            .where(_by_hand(), Transaction.merchant_key.in_(keys[start : start + IN_BATCH]))
            .order_by(Transaction.transaction_id)
        )
        for t in rows:
            seen[t.merchant_key or ""].append(t)
    out = []
    for key, lines in seen.items():
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
    """A rule saved from a suggestion and the lines it took."""

    rule_id: int
    pattern: str
    lines: int  # other lines the new rule categorized


def learn(db: Session, t: Transaction, user: str) -> Learned | None:
    """After a category chosen by hand: when this merchant now has MIN_TIMES lines categorized by
    hand, all to one category, and no rule knows it, save the rule and apply it to the lines
    still waiting (ADR-079). Never for a bare transfer text ("TRANSFERENCIA INTERNET": it names
    no one), a merchant whose rule was deleted or turned off, or one categorized two ways."""
    key = rule_engine.key(t.description_raw or "")
    if t.category_id is None or len(key) < MIN_KEY or not rule_engine.rule_ok(key):
        return None
    if db.scalar(select(MerchantRule.rule_id).where(MerchantRule.pattern == key).limit(1)):
        return None  # there was a rule once: a person removed it or turned it off
    rules = [
        rule_engine.Rule.of(r)
        for r in db.scalars(select(MerchantRule).where(MerchantRule.is_active))
    ]
    if rule_engine.first_match(rules, t.description_raw, t.amount):
        return None
    db.flush()  # this line's key and category are in the database before it's asked
    same = list(db.scalars(select(Transaction).where(_by_hand(), Transaction.merchant_key == key)))
    if len(same) < MIN_TIMES or {x.category_id for x in same} != {t.category_id}:
        return None
    people = {x.person for x in same}
    rule = MerchantRule(
        pattern=key,
        match_type="contains",
        category_id=t.category_id,
        priority=rule_engine.REVIEW_RULE_PRIORITY,
        set_person=who if len(people) == 1 and (who := next(iter(people))) in OWNERS else None,
    )
    db.add(rule)
    db.flush()
    lines = classify.apply_rule(db, rule, user + " (learned)")
    db.commit()
    return Learned(rule.rule_id, key, lines)
