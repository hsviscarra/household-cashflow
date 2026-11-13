"""The Inbox doing more of the work (ADR-029).

- **Autopilot**: after a statement is approved on its own (ADR-024), Claude is asked about the
  new merchants and every suggestion at or above AUTO_ACCEPT_CONFIDENCE (0.90) is accepted with
  a rule, as if accepted by hand. Lower ones wait in the Inbox.
- **Recently accepted on their own**: the rules autopilot saved in the last 30 days, with how
  many lines each categorized, so a wrong one is seen; **undo** turns the rule off and puts its
  lines back in the Inbox as they were.
- **Many at once**: several merchants to one category (or each to its suggestion) in one call.
- **Who?**: transfers that say only "TRANSFERENCIA", "ZELLE" or the like and have no person:
  pick the person and the line gets them (and their category, unless someone chose one).
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FROM_BANKS, Category, ChangeLog, Counterparty, MerchantRule, Transaction
from app.services import classify, people, transfers
from app.services import suggest as suggestions

log = logging.getLogger(__name__)

AUTO = " (automatic)"  # as stage.AUTO: who did it, in audit.change_log
RECENT_DAYS = 30
WHO_DAYS = 90
# Descriptions that say a transfer happened but not to whom.
TRANSFER_TEXT = re.compile(
    r"TRANSF|ZELLE|INTERBANC|\bSPI\b|PAGO DIRECTO|DEPOSITO|DEPÓSITO|CREDITO RECIBIDO|ENVIO"
)


class InboxError(Exception):
    """An Inbox action that can't be done; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Autopilot:
    """What the automatic categorization did after a load."""

    asked: int = 0
    suggested: int = 0
    merchants: int = 0
    lines: int = 0


def autopilot(db: Session, user: str) -> Autopilot:
    """Ask Claude about new merchants and accept the sure ones. Never raises: a failure leaves
    everything in the Inbox, as before."""
    threshold = get_settings().auto_accept_confidence
    done = Autopilot()
    if threshold <= 0 or not suggestions.available():
        return done
    try:
        done.asked, done.suggested = suggestions.suggest(db)
        accepted = classify.accept_suggestions(
            db, user if user.endswith(AUTO) else user + AUTO, min_confidence=threshold
        )
    except Exception:  # Claude down, a bad answer: the lines wait in the Inbox
        db.rollback()
        log.exception("Autopilot didn't finish")
        return done
    done.merchants, done.lines = accepted.merchants, accepted.lines + accepted.also_by_rule
    return done


# ---------------------------------------------------------------- recently accepted on their own
@dataclass
class AutoRule:
    """A rule made on its own from a confident suggestion."""

    rule_id: int
    pattern: str
    category_id: int
    lines: int
    accepted_at: datetime
    is_active: bool


def _auto_changes(db: Session, since: datetime) -> list[ChangeLog]:
    return list(
        db.scalars(
            select(ChangeLog)
            .where(
                ChangeLog.table_name == "core.transaction",
                ChangeLog.column_name.in_(("category_id", "type")),
                ChangeLog.changed_by.like(f"%{AUTO}"),
                ChangeLog.changed_at >= since,
            )
            .order_by(ChangeLog.change_id)
        )
    )


def recent_auto(db: Session, days: int = RECENT_DAYS) -> list[AutoRule]:
    """Rules autopilot saved lately, with the lines still categorized by them."""
    since = datetime.now() - timedelta(days=days)
    changed = {c.row_id: c for c in _auto_changes(db, since) if c.column_name == "category_id"}
    if not changed:
        return []
    rows = db.scalars(
        select(Transaction).where(
            Transaction.transaction_id.in_(list(changed)[:2000]),
            Transaction.rule_id.is_not(None),
        )
    )
    by_rule: dict[int, list[Transaction]] = {}
    for t in rows:
        if str(t.category_id) == changed[t.transaction_id].new_value:
            by_rule.setdefault(int(t.rule_id or 0), []).append(t)
    out = []
    for rule_id, lines in by_rule.items():
        rule = db.get(MerchantRule, rule_id)
        if rule is None:
            continue
        out.append(
            AutoRule(
                rule_id=rule_id,
                pattern=rule.pattern,
                category_id=rule.category_id,
                lines=len(lines),
                accepted_at=max(changed[t.transaction_id].changed_at for t in lines),
                is_active=rule.is_active,
            )
        )
    return sorted(out, key=lambda r: (r.accepted_at, r.rule_id), reverse=True)


def undo_auto(db: Session, rule_id: int, user: str) -> int:
    """Turn off a rule autopilot saved and put the lines it categorized back as they were
    (category and type from the change log). Lines changed since then by a person are left.
    Returns how many lines went back to the Inbox."""
    rule = db.get(MerchantRule, rule_id)
    if rule is None:
        raise InboxError(f"Rule {rule_id} not found.", 404)
    changes = _auto_changes(db, datetime(2000, 1, 1))
    first: dict[tuple[int, str], ChangeLog] = {}
    for c in changes:
        first.setdefault((c.row_id, c.column_name), c)
    ids = {row for row, col in first if col == "category_id"}
    rows = db.scalars(
        select(Transaction).where(
            Transaction.rule_id == rule_id,
            Transaction.transaction_id.in_(list(ids)[:2000]) if ids else Transaction.rule_id < 0,
        )
    )
    reason = f"Undo: rule {rule_id} accepted automatically"
    count = 0
    for t in rows:
        before = first[(t.transaction_id, "category_id")]
        if str(t.category_id) != before.new_value:
            continue  # someone changed it since
        kind = first.get((t.transaction_id, "type"))
        old_type = kind.old_value if kind and kind.old_value else t.type
        classify._log(db, t, "category_id", t.category_id, None, reason, user)
        classify._log(db, t, "type", t.type, old_type, reason, user)
        t.category_id = None
        t.type = old_type
        t.category_source = None
        t.rule_id = None
        count += 1
    rule.is_active = False
    db.commit()
    return count


# ---------------------------------------------------------------- many at once
@dataclass
class Many:
    """What categorizing several merchants did."""

    merchants: int = 0
    lines: int = 0
    also_by_rule: int = 0
    skipped: int = 0


def resolve_many(
    db: Session, keys: list[str], category_id: int | None, user: str, save_rule: bool = True
) -> Many:
    """Categorize several merchants: all to `category_id`, or (None) each to its suggestion."""
    done = Many()
    sugg = {g.merchant_key: g.suggestion for g in classify.review_groups(db)}
    for key in dict.fromkeys(keys):
        s = sugg.get(key)
        target = category_id if category_id is not None else (s.category_id if s else None)
        if target is None:
            done.skipped += 1
            continue
        try:
            r = classify.resolve(
                db,
                key,
                target,
                user,
                save_rule=save_rule,
                from_suggestion=category_id is None,
            )
        except classify.ClassifyError:
            db.rollback()  # categorized meanwhile, often by an earlier merchant's rule
            done.skipped += 1
            continue
        done.merchants += 1
        done.lines += r.categorized
        done.also_by_rule += r.also_by_rule
    return done


# ---------------------------------------------------------------- who?
def who_lines(
    db: Session, month: date | None = None, today: date | None = None
) -> list[Transaction]:
    """Transfers without a person whose description doesn't say who: the last 90 days, or a
    month. Card payments and transfers between your own accounts are left out."""
    paired = transfers._paired_categories(db)
    # Explained already: a line given an income, expense, savings or debt category (Salary from
    # an employer, rent paid by Zelle, a house installment) needs no person (ADR-047). Debt and
    # savings were missing: a house installment kept coming back (2026-11-10).
    explained = select(Category.category_id).where(
        Category.kind.in_(("income", "expense", "savings", "debt"))
    )
    q = select(Transaction).where(
        Transaction.source.in_(FROM_BANKS),
        Transaction.counterparty_id.is_(None),
        Transaction.transfer_group_id.is_(None),
        Transaction.parent_transaction_id.is_(None),
        Transaction.category_id.is_(None) | Transaction.category_id.not_in(paired),
        Transaction.category_id.is_(None) | Transaction.category_id.not_in(explained),
        ~classify._has_parts(),
    )
    if month:
        q = q.where(Transaction.cash_month == month.replace(day=1))
    else:
        q = q.where(Transaction.txn_date >= (today or date.today()) - timedelta(days=WHO_DAYS))
    rows = db.scalars(q.order_by(Transaction.txn_date.desc(), Transaction.transaction_id.desc()))
    return [t for t in rows if TRANSFER_TEXT.search(t.description_raw.upper())]


def set_who(db: Session, transaction_id: int, counterparty_id: int, user: str) -> Transaction:
    """Link a transfer line to a person, logging the change."""
    row = db.get(Transaction, transaction_id)
    if row is None:
        raise InboxError(f"Line {transaction_id} not found.", 404)
    person = db.get(Counterparty, counterparty_id)
    if person is None:
        raise InboxError(f"Person {counterparty_id} not found.", 404)
    people._apply(db, row, person, person.category_id, "person", f"Inbox: {person.name}", user)
    db.commit()
    return row
