"""Merchant rule matching: the first active rule (lowest priority number) that matches wins.

Used by the Settings page rule tester, classification during imports and the review queue (F9).
A rule may also carry a range on the absolute amount: "PAGO IESS" under 300 is the empleada's IESS,
above it the BIESS house loan.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class RuleRow(Protocol):
    """What the matcher needs from a rule, whether stored or just typed."""

    rule_id: int
    pattern: str
    match_type: str
    category_id: int
    priority: int
    is_active: bool
    amount_min: Decimal | None
    amount_max: Decimal | None
    set_person: str | None
    merchant_name: str | None


@dataclass(frozen=True)
class Rule:
    """A merchant rule as the matcher reads it."""

    rule_id: int
    pattern: str
    match_type: str
    category_id: int
    priority: int
    is_active: bool = True
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    set_person: str | None = None  # ADR-042: whose line it is
    merchant_name: str | None = None  # ADR-042: the name lines get

    @classmethod
    def of(cls, r: RuleRow) -> "Rule":
        """A rule from its database row."""
        return cls(
            r.rule_id,
            r.pattern,
            r.match_type,
            r.category_id,
            r.priority,
            r.is_active,
            r.amount_min,
            r.amount_max,
            getattr(r, "set_person", None),
            getattr(r, "merchant_name", None),
        )

    def merchant(self) -> str:
        """The merchant name a matched line gets: the rule's name, or its pattern."""
        return (self.merchant_name or self.pattern.strip(" *"))[:100]


MAX_KEY = 200  # characters of a merchant key (core.merchant_rule.pattern holds as many)


def normalize(text: str) -> str:
    """Uppercase and collapse whitespace so statement descriptions compare consistently."""
    return " ".join(text.upper().split())


def key(description: str) -> str:
    """What groups lines of the same merchant: uppercase, reference numbers (4+ digits) and
    store numbers and confirmation codes dropped, so "MICROSOFT*123456 MSBILL" and
    "MICROSOFT*987654 MSBILL" are one, and so are two Zelle payments to the same person.

    Stored on every line as `core.transaction.merchant_key` (ADR-086): a change here needs a
    migration that recomputes the column."""
    text = normalize(description)
    # Confirmation and payment codes ("CONF# AB12CD34E", "ID:PAYCO1234X"): letters and digits mixed.
    text = re.sub(r"\b(?:CONF#|ID:)\s*\S+", " ", text)
    text = re.sub(r"\b(?=[A-Z]*\d)(?=\d*[A-Z])[A-Z\d]{6,}\b", " ", text)
    text = re.sub(r"[#*]?\d{4,}", " ", text)
    text = re.sub(r"\s#?\d{1,3}\b", " ", text)
    return " ".join(text.split())[:MAX_KEY]


def in_range(rule: Rule, amount: Decimal | None) -> bool:
    """No range, or the absolute amount inside it. A ranged rule never matches without an amount."""
    if rule.amount_min is None and rule.amount_max is None:
        return True
    if amount is None:
        return False
    size = abs(amount)
    low_ok = rule.amount_min is None or size >= rule.amount_min
    return low_ok and (rule.amount_max is None or size <= rule.amount_max)


def matches(rule: Rule, description: str, amount: Decimal | None = None) -> bool:
    """Whether a rule matches a description (and an amount, when the rule has a range)."""
    if not in_range(rule, amount):
        return False
    text = normalize(description)
    pattern = normalize(rule.pattern)
    if rule.match_type == "contains":
        # Rules saved from To do and Review carry the merchant key, which drops the numbers in
        # the middle of a description ("PRIME VIDEO *2X4 888-802-3080" -> "PRIME VIDEO * -802-"):
        # the key of the line is compared too, or such a rule would never match (ADR-085).
        return pattern in text or pattern in key(description)
    if rule.match_type == "starts_with":
        return text.startswith(pattern)
    if rule.match_type == "regex":
        try:
            return re.search(rule.pattern, description, flags=re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def first_match(
    rules: Iterable[Rule], description: str, amount: Decimal | None = None
) -> Rule | None:
    """The first active rule that matches, in priority order; None when none does."""
    for rule in sorted(rules, key=lambda r: (r.priority, r.rule_id)):
        if rule.is_active and matches(rule, description, amount):
            return rule
    return None


def validate_pattern(pattern: str, match_type: str) -> str | None:
    """Returns an error message for an unusable pattern, or None when it is fine."""
    if not pattern.strip():
        return "Pattern can't be empty."
    if match_type == "regex":
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"Not a valid regular expression: {exc}"
    return None


# Lower than the seeded merchant rules (10-30): a rule saved while reviewing is specific.
REVIEW_RULE_PRIORITY = 15

# Words of descriptions that say nothing about who or what ("TRANSFERENCIA INTERNET", "SU PAGO
# MUCHAS GRACIAS"): a rule on them would catch unrelated payments, so Always is off for them.
GENERIC_WORDS = frozenset(
    (
        "TRANSFERENCIA",
        "TRANSFERENCIAS",
        "INTERNET",
        "SU",
        "PAGO",
        "PAGOS",
        "MUCHAS",
        "GRACIAS",
        "DEPOSITO",
        "DEPOSITOS",
        "TRANSFER",
        "ONLINE",
        "BANKING",
        "RETIRO",
        "CAJERO",
        "ATM",
        "NOTA",
        "CREDITO",
        "DEBITO",
        "ENVIADA",
        "RECIBIDA",
        "INTERBANCARIA",
        "INTERBANCARIO",
        "DE",
        "A",
        "POR",
        "EN",
        "MOVIL",
        "BANCA",
        "WEB",
        "TO",
        "FROM",
        "PAYMENT",
        "MOBILE",
        "CTA",
        "CTAS",
        "CUENTA",
        "CUENTAS",
        "TERCEROS",
        "TERCERO",
        "BCA",
        "BCO",
        "BANCO",
        "BANCOS",
        "ENL",
        "LINEA",
        "OTROS",
        "OTRAS",
        "ENVIO",
        "ENVIADO",
        "SPI",
        "DIRECTO",
        "DIRECTA",
        "INTERNA",
        "INTERNO",
        "PROPIAS",
        "PROPIA",
        "AHORROS",
        "CORRIENTE",
        "TRANSF",
        "TRF",
        "ZELLE",
    )
)


def rule_ok(merchant_key: str | None) -> bool:
    """Whether a rule on this description would be safe: it names someone or something."""
    words = (merchant_key or "").upper().replace("*", " ").split()
    return bool(words) and not all(w in GENERIC_WORDS for w in words)
