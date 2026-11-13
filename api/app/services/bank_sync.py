"""Bank sync through SimpleFIN Bridge (ADR-044).

Once a day at most, the movements of the accounts linked to SimpleFIN (Bank of America and
Capital One) are read and kept as pending lines (source 'bank_sync'), categorized by the rules
like any statement line. When the month's statement is approved it takes their place: each
statement line takes over the matching synced line's category, person, notes and links, and the
synced lines of that period are removed. The statement stays the record that must tie out.

The access URL holds the credentials: it comes only from the SIMPLEFIN_ACCESS_URL setting and is
never logged, stored or returned.
"""

import base64
import hashlib
import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import outside
from app.config import get_settings
from app.models import (
    Account,
    Category,
    ChangeLog,
    ImportBatch,
    Invoice,
    LoadLog,
    MerchantRule,
    StatementFileAccount,
    StatementHeader,
    Transaction,
    TransferNote,
)
from app.services import classify, payday
from app.services import rules as rule_engine

SOURCE = "bank_sync"
LOOKBACK = timedelta(days=44)  # SimpleFIN recommends 45 days or fewer (90 at most)
EVERY = timedelta(hours=12)  # SimpleFIN asks for 24 requests a day or fewer; we use 2 at most
MATCH_DAYS = 5  # a statement line and its synced line: same account and amount, dates this close

Fetch = Callable[[str, dict[str, str]], dict[str, Any]]


class SyncError(Exception):
    """The bank sync can't be done; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class SyncResult:
    """What a sync did: lines added, already here or covered by a statement, and accounts not
    linked."""

    added: int = 0
    already: int = 0
    covered: int = 0  # dated inside a statement already loaded
    unlinked: int = 0  # movements of SimpleFIN accounts not linked to an app account
    accounts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def configured() -> bool:
    """Whether a SimpleFIN access URL is set."""
    return bool(get_settings().simplefin_access_url)


def _http_get(url: str, headers: dict[str, str]) -> dict[str, Any]:  # pragma: no cover - network
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return body


def _request(access_url: str, start: date) -> tuple[str, dict[str, str]]:
    """The /accounts URL without the credentials, and the Basic header that carries them."""
    parts = urllib.parse.urlsplit(access_url)
    if parts.scheme != "https" or not parts.hostname:
        raise SyncError("The SimpleFIN access URL is not valid; run setup-simplefin.sh again.")
    netloc = parts.hostname + (f":{parts.port}" if parts.port else "")
    since = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    query = urllib.parse.urlencode({"start-date": since})
    url = urllib.parse.urlunsplit(
        ("https", netloc, parts.path.rstrip("/") + "/accounts", query, "")
    )
    user = urllib.parse.unquote(parts.username or "")
    password = urllib.parse.unquote(parts.password or "")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return url, {"Authorization": f"Basic {token}", "User-Agent": "household-cashflow"}


def _money(value: object) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        return None


def _day(epoch: object) -> date | None:
    try:
        return datetime.fromtimestamp(int(str(epoch)), UTC).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def natural_key(sync_account: str, sync_txn: str) -> str:
    """A synced line's identity: the bank's account and transaction ids, hashed."""
    return "sf:" + hashlib.sha256(f"{sync_account}|{sync_txn}".encode()).hexdigest()[:61]


def statement_end(db: Session, account_id: int) -> date | None:
    """The last day the account's loaded statements cover."""
    end = db.scalar(
        select(func.max(StatementHeader.period_end))
        .join(
            StatementFileAccount,
            StatementFileAccount.statement_file_id == StatementHeader.statement_file_id,
        )
        .join(ImportBatch, ImportBatch.statement_file_id == StatementHeader.statement_file_id)
        .where(StatementFileAccount.account_id == account_id, ImportBatch.status == "approved")
    )
    return end


def last_run(db: Session) -> LoadLog | None:
    """The latest sync's log entry, or None when it never ran."""
    return db.scalars(
        select(LoadLog).where(LoadLog.source == SOURCE).order_by(LoadLog.load_id.desc()).limit(1)
    ).first()


def newly_linked(db: Session, last: LoadLog | None) -> bool:
    """Whether an account is linked now that wasn't at the last run (so a sync can't wait)."""
    if last is None:
        return False
    try:
        before = {a["sync_id"]: a.get("account_id") for a in json.loads(last.summary)["accounts"]}
    except (ValueError, KeyError, TypeError):
        return False
    now = set(db.scalars(select(Account.sync_id).where(Account.sync_id.is_not(None))))
    return any(sid in before and before[sid] is None for sid in now)


def due(db: Session, now: datetime | None = None) -> bool:
    """Whether a sync may run: set up, and the last one at least EVERY ago."""
    if not configured():
        return False
    last = last_run(db)
    now = now or datetime.now(UTC).replace(tzinfo=None)
    return last is None or now - last.loaded_at >= EVERY


def sync(
    db: Session, user: str, today: date | None = None, fetch: Fetch | None = None
) -> SyncResult:
    """Fetch the linked accounts' posted lines from SimpleFIN, add the new ones with a category
    from the rules, and record balances; `fetch` replaces the network call in tests."""
    access = get_settings().simplefin_access_url
    if not access:
        raise SyncError("Bank sync isn't set up; run infra/azure/setup-simplefin.sh.")
    today = today or date.today()
    url, headers = _request(access, today - LOOKBACK)
    get = fetch or _http_get
    try:
        # The real call is tried again on a blip; an injected one (tests) is called once.
        data = get(url, headers) if fetch else outside.retry(lambda: get(url, headers))
    except outside.NETWORK_ERRORS as e:  # never echo the URL: it carries the credentials
        raise SyncError(f"SimpleFIN didn't answer ({type(e).__name__}).", 502) from None

    result = SyncResult(errors=[str(x)[:200] for x in data.get("errors") or []])
    linked = {a.sync_id: a for a in db.scalars(select(Account).where(Account.sync_id.is_not(None)))}
    active = db.scalars(select(MerchantRule).where(MerchantRule.is_active))
    rules = [rule_engine.Rule.of(r) for r in active]
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    added: list[Transaction] = []
    for acct in data.get("accounts") or []:
        sid = str(acct.get("id") or "")[:100]
        account = linked.get(sid)
        txns = [t for t in acct.get("transactions") or [] if not t.get("pending")]
        result.accounts.append(
            {
                "sync_id": sid,
                "org": str((acct.get("org") or {}).get("name") or "")[:100],
                "name": str(acct.get("name") or "")[:100],
                "balance": str(_money(acct.get("balance")) or ""),
                "balance_date": str(_day(acct.get("balance-date")) or ""),
                "account_id": account.account_id if account else None,
                "movements": len(txns),
            }
        )
        if account is None:
            result.unlinked += len(txns)
            continue
        covered_to = statement_end(db, account.account_id)
        keys = {natural_key(sid, str(t.get("id"))): t for t in txns if t.get("id")}
        have = (
            set(
                db.scalars(select(Transaction.natural_key).where(Transaction.natural_key.in_(keys)))
            )
            if keys
            else set()
        )
        for key, t in keys.items():
            amount, day = _money(t.get("amount")), _day(t.get("transacted_at") or t.get("posted"))
            if amount is None or day is None or amount == 0:
                continue
            if key in have:
                result.already += 1
                continue
            if covered_to is not None and day <= covered_to:
                result.covered += 1
                continue
            row = _row(account, key, day, amount, t, rules, cats)
            db.add(row)
            added.append(row)
    result.added = len(added)
    db.add(
        LoadLog(
            source=SOURCE,
            loaded_by=user,
            rows_loaded=result.added,
            summary=json.dumps(
                {
                    "added": result.added,
                    "already": result.already,
                    "covered": result.covered,
                    "unlinked": result.unlinked,
                    "accounts": result.accounts,
                    "errors": result.errors,
                }
            ),
        )
    )
    db.commit()
    return result


def _row(
    account: Account,
    key: str,
    day: date,
    amount: Decimal,
    t: dict[str, Any],
    rules: list[rule_engine.Rule],
    cats: dict[int, Category],
) -> Transaction:
    description = " ".join(
        str(t.get("description") or t.get("payee") or t.get("memo") or "").split()
    )[:400]
    hit = rule_engine.first_match(rules, description, amount)
    cat = cats.get(hit.category_id) if hit else None
    if hit and cat:
        type_ = classify.rule_type(cat.kind, account, amount)
    else:
        type_ = classify.rule_type("expense", account, amount)
    return Transaction(
        natural_key=key,
        account_id=account.account_id,
        txn_date=day,
        post_date=_day(t.get("posted")),
        cash_month=payday.cash_month(day, description or "", amount),
        amount=amount,
        description_raw=description or "(no description)",
        merchant=hit.merchant() if hit else classify.merchant_key(description)[:200] or None,
        type=type_,
        category_id=cat.category_id if cat else None,
        rule_id=hit.rule_id if hit and cat else None,
        category_source="rule" if hit and cat else None,
        person=(hit.set_person if hit else None) or account.owner,
        country=account.country,
        is_fixed=bool(cat and cat.is_fixed),
        source=SOURCE,
        status="pending",
    )


# ---------------------------------------------------------------- the statement takes over
CARRY = ("category_id", "category_source", "rule_id", "type", "person", "notes", "is_fixed")
LINKS = ("transfer_group_id", "recurring_entry_id", "counterparty_id")


def absorb(db: Session, loaded: list[Transaction], user: str) -> tuple[int, int]:
    """After a statement is loaded: each of its lines takes the place of the synced line with
    the same account and amount within MATCH_DAYS (closest date first), keeping what was done to
    it by hand; then every synced line of those accounts dated inside the statement is removed.
    Returns (matched, removed). Runs inside the caller's transaction."""
    if not loaded:
        return 0, 0
    span: dict[int, tuple[date, date]] = {}
    for t in loaded:
        if t.account_id is None:
            continue
        lo, hi = span.get(t.account_id, (t.txn_date, t.txn_date))
        span[t.account_id] = (min(lo, t.txn_date), max(hi, t.txn_date))
    matched = removed = 0
    for account_id, (lo, hi) in span.items():
        synced = list(
            db.scalars(
                select(Transaction).where(
                    Transaction.source == SOURCE,
                    Transaction.account_id == account_id,
                    Transaction.txn_date >= lo - timedelta(days=MATCH_DAYS),
                    Transaction.txn_date <= hi + timedelta(days=MATCH_DAYS),
                )
            )
        )
        if not synced:
            continue
        free = list(synced)
        for t in sorted(
            (x for x in loaded if x.account_id == account_id), key=lambda x: x.txn_date
        ):
            near = [
                s
                for s in free
                if s.amount == t.amount and abs((s.txn_date - t.txn_date).days) <= MATCH_DAYS
            ]
            if not near:
                continue
            s = min(near, key=lambda x: (abs((x.txn_date - t.txn_date).days), x.transaction_id))
            free.remove(s)
            _take_over(db, s, t, user)
            matched += 1
        # Synced lines inside the statement's dates that matched nothing: the statement, which
        # ties out, is complete, so they were never real lines (or changed before posting).
        for s in free:
            if lo <= s.txn_date <= hi:
                _drop(db, s, None, user)
                removed += 1
    return matched, removed


def _take_over(db: Session, s: Transaction, t: Transaction, user: str) -> None:
    hand = s.category_source in ("manual", "suggestion", "match", "note", "person", "split")
    if hand or (t.category_id is None and s.category_id is not None):
        for col in CARRY:
            setattr(t, col, getattr(s, col))
    elif s.person != t.person and s.person is not None:
        t.person = s.person
    if s.notes and not t.notes:
        t.notes = s.notes
    for col in LINKS:
        if getattr(s, col) is not None and getattr(t, col) is None:
            setattr(t, col, getattr(s, col))
    _drop(db, s, t, user)


def _drop(db: Session, s: Transaction, t: Transaction | None, user: str) -> None:
    db.flush()
    target = t.transaction_id if t is not None else None
    for model, col in (
        (Transaction, Transaction.parent_transaction_id),
        (TransferNote, TransferNote.transaction_id),
        (Invoice, Invoice.transaction_id),
    ):
        db.execute(update(model).where(col == s.transaction_id).values({col.key: target}))
    db.add(
        ChangeLog(
            table_name="core.transaction",
            row_id=s.transaction_id,
            column_name="source",
            old_value=SOURCE,
            new_value=None if target is None else f"statement line {target}",
            reason="bank sync line replaced by its statement"[:200],
            changed_by=user,
        )
    )
    db.delete(s)
