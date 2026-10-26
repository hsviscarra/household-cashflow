"""Claude's category suggestions for merchants no rule knows (F9, ADR-006).

Only what is needed leaves the server: each merchant's description as printed, amounts, dates and
the bank's name and country. No account numbers, no names of people, no balances. Claude answers
with JSON that must follow a schema whose category is one of Hernan's own category paths, plus a
confidence from 0 to 1 and a short reason. Suggestions are stored and shown in the review queue;
nothing is categorized until Hernan accepts one.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion.preview import category_paths
from app.models import Account, Category, MerchantSuggestion, Transaction
from app.services import classify

log = logging.getLogger(__name__)

MAX_MERCHANTS = 40  # per click; a month rarely has more unknown merchants
PER_CALL = 20  # merchants per request, so each answer stays short
# Claude Haiku 5.5 thinks before answering and the thinking counts toward max_tokens: low effort
# (the documented setting for simple, high-volume classification) and room for the answer.
EFFORT: Final = "low"
MAX_TOKENS = 16000
SAMPLES = 3  # lines shown per merchant

SYSTEM = (
    "You categorize household bank and credit card transactions for a family in Quito, Ecuador, "
    "that also has US accounts. Amounts are USD; negative means money out. For each merchant, "
    "pick the single best category path from the list given, a confidence from 0 to 1 (how sure "
    "you are this merchant belongs there), and a reason of at most 15 words. Use a low confidence "
    "when the description is ambiguous (for example a bare bank transfer). Spanish descriptions "
    "are common: TRANSFERENCIA = transfer, DEBITO = debit, PAGO = payment, CONSUMO = purchase."
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


@dataclass
class Answer:
    merchant_key: str
    category_path: str
    confidence: Decimal
    reason: str


def _schema(paths: list[str], keys: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "merchant_key": {"type": "string", "enum": keys},
                        "category_path": {"type": "string", "enum": paths},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["merchant_key", "category_path", "confidence", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["suggestions"],
        "additionalProperties": False,
    }


def call_claude(asked: list[Asked], categories: list[str]) -> list[Answer]:
    """One Messages API call with a JSON-schema answer. Replaced in tests."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60)
    payload = {
        "categories": categories,
        "merchants": [{"merchant_key": a.merchant_key, "lines": a.lines} for a in asked],
    }
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
                    "schema": _schema(categories, [a.merchant_key for a in asked]),
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
        return parse_answer(text)
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


def parse_answer(text: str) -> list[Answer]:
    """The suggestions in Claude's reply. Tolerant of a code fence or words around the JSON, of a
    bare list instead of {"suggestions": [...]}, and of "merchant"/"category" for the field names;
    an item without a merchant or category is skipped. ValueError when nothing can be read."""
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
        key = item.get("merchant_key") or item.get("merchant")
        path = item.get("category_path") or item.get("category")
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


def suggest(db: Session, month: date | None = None) -> tuple[int, int]:
    """Ask Claude about the uncategorized merchants that have no suggestion yet.
    Returns (merchants asked, suggestions stored)."""
    if not available():
        raise SuggestError("Suggestions are off: set ANTHROPIC_API_KEY on the server.", 503)
    groups = [g for g in classify.review_groups(db, month) if g.suggestion is None]
    groups = groups[:MAX_MERCHANTS]
    if not groups:
        return 0, 0

    accounts = {a.account_id: a for a in db.scalars(select(Account))}
    ids = [ln.transaction_id for g in groups for ln in g.lines]
    rows = {
        t.transaction_id: t
        for t in db.scalars(select(Transaction).where(Transaction.transaction_id.in_(ids)))
    }
    asked = []
    for g in groups:
        lines = []
        for ln in g.lines[:SAMPLES]:
            account = accounts.get(rows[ln.transaction_id].account_id or -1)
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
        asked.append(Asked(g.merchant_key, lines))

    paths = category_paths(db)
    by_path = {_fold(p): cid for cid, p in paths.items()}
    # Groups only (no subcategories) are offered when they have no children.
    parents = {c.parent_id for c in db.scalars(select(Category)) if c.parent_id is not None}
    offered = sorted(p for cid, p in paths.items() if cid not in parents)

    answers = [
        a
        for i in range(0, len(asked), PER_CALL)
        for a in call_claude(asked[i : i + PER_CALL], offered)
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
