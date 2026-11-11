"""Claude's category suggestions for merchants no rule knows (F9, ADR-006).

Only what is needed leaves the server: each merchant's description as printed, amounts, dates and
the bank's name and country, and (ADR-077) what the app already knows about the line: whose it is
(Hernan, Lauren, Juliana), the purpose of the card it is on, the category of earlier lines of the
same amount, the products of an invoice of that amount, and a few recent choices made by hand as
examples. No account numbers, no balances, no cédulas. Claude answers
with JSON that must follow a schema whose category is one of Hernan's own category paths, plus a
confidence from 0 to 1 and a short reason. Suggestions are stored and shown in the review queue;
nothing is categorized until Hernan accepts one.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.ingestion.preview import category_paths
from app.models import Account, Category, Invoice, MerchantSuggestion, Transaction
from app.services import classify, line_context

log = logging.getLogger(__name__)

MAX_MERCHANTS = 40  # per click; a month rarely has more unknown merchants
PER_CALL = 20  # merchants per request, so each answer stays short
# Claude Haiku 5.5 thinks before answering and the thinking counts toward max_tokens: low effort
# (the documented setting for simple, high-volume classification) and room for the answer.
EFFORT: Final = "low"
MAX_TOKENS = 16000
SAMPLES = 3  # lines shown per merchant
EXAMPLES = 25  # recent choices made by hand, sent as examples (ADR-077)
SAME_AMOUNT = 3  # earlier lines of the same amount, per merchant
INVOICE_DAYS = 5  # an invoice of the same amount this close to the line
PRODUCTS = 5  # of an invoice, largest first

SYSTEM = (
    "You categorize household bank and credit card transactions for a family in Quito, Ecuador, "
    "that also has US accounts. Amounts are USD; negative means money out. For each merchant "
    "(by its id), pick the single best category (by its id) from the list given, a confidence "
    "from 0 to 1 (how sure "
    "you are this merchant belongs there), and a reason of at most 15 words. Use a low confidence "
    "when the description is ambiguous (for example a bare bank transfer). Spanish descriptions "
    "are common: TRANSFERENCIA = transfer, DEBITO = debit, PAGO = payment, CONSUMO = purchase. "
    "A category's description, when given, is the family's own rule for what belongs there: "
    "follow it over your general sense of the word. A merchant may come with context the family's "
    "app already has: person (whose line it is), card_purpose (what that card is kept for), "
    "same_amount_before (earlier lines of exactly this amount and the category they got: a "
    "repeating amount is usually the same bill), and invoice (the seller and products of an "
    "electronic invoice of this amount, days apart: the strongest evidence of what was bought). "
    "examples are recent choices the family made by hand: prefer their way of categorizing."
)


class SuggestError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def available() -> bool:
    return bool(get_settings().anthropic_api_key)


@dataclass
class Asked:
    merchant_key: str
    lines: list[dict[str, Any]]
    context: dict[str, Any] | None = None  # what the app knows about these lines (ADR-077)


@dataclass
class Answer:
    merchant_key: str
    category_path: str
    confidence: Decimal
    reason: str


def _schema(category_ids: list[str], merchant_ids: list[str]) -> dict[str, Any]:
    """Claude answers with short ids only ("m1", "c3"). Repeating a description with double
    quotes ('ZELLE ... FOR "AN ORDER";') inside the JSON broke it: the quotes came back
    unescaped."""
    return {
        "type": "object",
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "merchant_id": {"type": "string", "enum": merchant_ids},
                        "category_id": {"type": "string", "enum": category_ids},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["merchant_id", "category_id", "confidence", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["suggestions"],
        "additionalProperties": False,
    }


def call_claude(
    asked: list[Asked],
    categories: list[str],
    descriptions: dict[str, str] | None = None,
    examples: list[dict[str, str]] | None = None,
) -> list[Answer]:
    """One Messages API call with a JSON-schema answer. Replaced in tests. `descriptions` (by
    path) say what goes in each category, as Hernan wrote them (F23); `examples` are recent
    choices made by hand (ADR-077)."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60)
    merchant_ids = {f"m{i}": a.merchant_key for i, a in enumerate(asked, start=1)}
    category_ids = {f"c{i}": path for i, path in enumerate(categories, start=1)}
    payload = {
        "categories": [
            {"id": cid, "path": path}
            | ({"description": descriptions[path]} if descriptions and path in descriptions else {})
            for cid, path in category_ids.items()
        ],
        "merchants": [
            {"id": mid, "lines": a.lines} | ({"context": a.context} if a.context else {})
            for mid, a in zip(merchant_ids, asked, strict=True)
        ],
    }
    if examples:
        payload["examples"] = examples
    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            output_config={
                "effort": EFFORT,
                "format": {
                    "type": "json_schema",
                    "schema": _schema(list(category_ids), list(merchant_ids)),
                },
            },
        )
    except anthropic.APIError as exc:
        raise SuggestError(f"Claude could not be reached: {exc.__class__.__name__}.") from exc
    stop = getattr(response, "stop_reason", None)
    if stop == "max_tokens":
        log.warning("Claude suggestions cut off at max_tokens (%s merchants)", len(asked))
        raise SuggestError(
            "Claude's answer was cut off; try again with fewer merchants (one month)."
        )
    if stop == "refusal":
        log.warning("Claude declined to suggest categories (%s merchants)", len(asked))
        raise SuggestError("Claude declined to answer this request.")
    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        return parse_answer(text, merchant_ids, category_ids)
    except ValueError as exc:
        # Merchant descriptions and category names only; no keys or account data.
        log.warning(
            "Claude suggestions unreadable: stop_reason=%s, %s characters, %s; starts: %r",
            stop,
            len(text),
            exc,
            text[:300],
        )
        raise SuggestError("Claude's answer could not be read.") from exc


def _fold(path: str) -> str:
    """'Groceries/Supermarket' and 'groceries / supermarket' name the same category."""
    return "".join(path.split()).casefold()


def parse_answer(
    text: str,
    merchant_ids: dict[str, str] | None = None,
    category_ids: dict[str, str] | None = None,
) -> list[Answer]:
    """The suggestions in Claude's reply. Tolerant of a code fence or words around the JSON, of a
    bare list instead of {"suggestions": [...]}, and of "merchant"/"category" for the field names;
    an item without a merchant or category is skipped. Ids ("m1", "c3") are mapped back to the
    merchant and category they stand for. ValueError when nothing can be read."""
    merchant_ids = merchant_ids or {}
    category_ids = category_ids or {}
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON in the reply")
    data, _ = json.JSONDecoder().raw_decode(text[start:])
    if isinstance(data, dict):
        items = data.get("suggestions")
        if items is None:
            items = next((v for v in data.values() if isinstance(v, list)), None)
    else:
        items = data
    if not isinstance(items, list):
        shape = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise ValueError(f"no list of suggestions ({shape})")
    answers = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("merchant_id") or item.get("merchant_key") or item.get("merchant")
        path = item.get("category_id") or item.get("category_path") or item.get("category")
        key = merchant_ids.get(str(key), key)
        path = category_ids.get(str(path), path)
        if not key or not path:
            continue
        try:
            confidence = Decimal(str(item.get("confidence", 0)))
        except ArithmeticError:
            confidence = Decimal(0)
        answers.append(Answer(str(key), str(path), confidence, str(item.get("reason", ""))))
    if items and not answers:
        first = sorted(items[0]) if isinstance(items[0], dict) else repr(items[0])
        raise ValueError(f"no usable item (first item: {first})")
    return answers


def hand_examples(
    db: Session, paths: dict[int, str], limit: int = EXAMPLES
) -> list[dict[str, str]]:
    """Recent categories a person chose by hand, one per merchant, newest first."""
    rows = db.scalars(
        select(Transaction)
        .where(Transaction.category_source == "manual", Transaction.category_id.is_not(None))
        .order_by(Transaction.txn_date.desc(), Transaction.transaction_id.desc())
        .limit(limit * 4)
    )
    seen: set[str] = set()
    out = []
    for t in rows:
        key = classify.merchant_key(t.description_raw or "")
        path = paths.get(t.category_id or 0)
        if not key or key in seen or path is None:
            continue
        seen.add(key)
        out.append({"description": key, "amount": str(t.amount), "category": path})
        if len(out) == limit:
            break
    return out


def context_for(
    db: Session,
    group: classify.ReviewGroup,
    paths: dict[int, str],
    purposes: dict[int, dict[str, object]],
) -> dict[str, Any] | None:
    """What the app already knows about a merchant's lines (ADR-077, as Transactions shows for
    one line, ADR-074): whose they are, the card's purpose, earlier lines of the same amount and
    an invoice of that amount."""
    out: dict[str, Any] = {}
    lines = group.lines[:SAMPLES]
    person = next((ln.person for ln in lines if ln.person), None)
    if person:
        out["person"] = person
    purpose = next((purposes[ln.account_id] for ln in lines if ln.account_id in purposes), None)
    if purpose:
        usual = purpose.get("usual")
        words = ", ".join(str(w) for w in usual) if isinstance(usual, list) else ""
        out["card_purpose"] = f"kept for {purpose.get('for')}" + (
            f"; its usual merchants: {words}" if words else ""
        )
    amounts = sorted({ln.amount for ln in lines})
    same = db.scalars(
        select(Transaction)
        .where(
            Transaction.amount.in_(amounts),
            Transaction.category_id.is_not(None),
            Transaction.source != "excel_history",
        )
        .order_by(Transaction.txn_date.desc())
        .limit(SAME_AMOUNT * 3)
    )
    before = []
    for t in same:
        path = paths.get(t.category_id or 0)
        if path is None or classify.merchant_key(t.description_raw or "") == group.merchant_key:
            continue
        before.append({"description": t.description_raw, "amount": str(t.amount), "category": path})
    if before:
        out["same_amount_before"] = before[:SAME_AMOUNT]
    for ln in lines:
        if ln.amount >= 0:
            continue
        inv = db.scalars(
            select(Invoice)
            .options(selectinload(Invoice.lines))
            .where(
                Invoice.total == -ln.amount,
                Invoice.issue_date >= ln.txn_date - timedelta(days=INVOICE_DAYS),
                Invoice.issue_date <= ln.txn_date + timedelta(days=INVOICE_DAYS),
            )
            .limit(1)
        ).first()
        if inv is not None:
            top = sorted(inv.lines, key=lambda x: -x.total)[:PRODUCTS]
            out["invoice"] = {
                "seller": inv.issuer_name,
                "products": [x.description for x in top],
            }
            break
    return out or None


def suggest(db: Session, month: date | None = None, batch_id: int | None = None) -> tuple[int, int]:
    """Ask Claude about the uncategorized merchants that have no suggestion yet: a month's
    loaded lines, or one statement waiting for approval (F23).
    Returns (merchants asked, suggestions stored)."""
    if not available():
        raise SuggestError("Suggestions are off: set ANTHROPIC_API_KEY on the server.", 503)
    found = (
        classify.batch_groups(db, batch_id)
        if batch_id is not None
        else classify.review_groups(db, month)
    )
    groups = [g for g in found if g.suggestion is None][:MAX_MERCHANTS]
    if not groups:
        return 0, 0

    accounts = {a.account_id: a for a in db.scalars(select(Account))}
    paths = category_paths(db)
    purposes = line_context.purposes(db)
    asked = []
    for g in groups:
        lines = []
        for ln in g.lines[:SAMPLES]:
            account = accounts.get(ln.account_id or -1)
            lines.append(
                {
                    "description": ln.description,
                    "amount": str(ln.amount),
                    "date": ln.txn_date.isoformat(),
                    "bank": account.institution if account else None,
                    "country": account.country if account else None,
                    "card_or_account": account.kind if account else None,
                }
            )
        asked.append(Asked(g.merchant_key, lines, context_for(db, g, paths, purposes)))

    by_path = {_fold(p): cid for cid, p in paths.items()}
    # Groups only (no subcategories) are offered when they have no children.
    parents = {c.parent_id for c in db.scalars(select(Category)) if c.parent_id is not None}
    offered = sorted(p for cid, p in paths.items() if cid not in parents)
    notes = {
        paths[c.category_id]: c.description
        for c in db.scalars(select(Category))
        if c.description and c.category_id not in parents
    }

    examples = hand_examples(db, paths)
    answers = [
        a
        for i in range(0, len(asked), PER_CALL)
        for a in call_claude(asked[i : i + PER_CALL], offered, notes, examples)
    ]
    keys = {a.merchant_key for a in asked}
    model = get_settings().anthropic_model
    stored = 0
    for a in answers:
        cid = by_path.get(_fold(a.category_path))
        if a.merchant_key not in keys or cid is None:
            continue  # the schema prevents this; never trust it blindly
        confidence = min(max(a.confidence, Decimal(0)), Decimal(1)).quantize(Decimal("0.001"))
        existing = db.scalar(
            select(MerchantSuggestion).where(MerchantSuggestion.merchant_key == a.merchant_key)
        )
        if existing is None:
            existing = MerchantSuggestion(merchant_key=a.merchant_key)
            db.add(existing)
        existing.category_id = cid
        existing.confidence = confidence
        existing.reason = a.reason[:400]
        existing.model = model
        stored += 1
    db.commit()
    return len(asked), stored
