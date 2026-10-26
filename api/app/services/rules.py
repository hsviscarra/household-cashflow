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
    rule_id: int
    pattern: str
    match_type: str
    category_id: int
    priority: int
    is_active: bool
    amount_min: Decimal | None
    amount_max: Decimal | None


@dataclass(frozen=True)
class Rule:
    rule_id: int
    pattern: str
    match_type: str
    category_id: int
    priority: int
    is_active: bool = True
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None

    @classmethod
    def of(cls, r: RuleRow) -> "Rule":
        return cls(
            r.rule_id,
            r.pattern,
            r.match_type,
            r.category_id,
            r.priority,
            r.is_active,
            r.amount_min,
            r.amount_max,
        )


def normalize(text: str) -> str:
    """Uppercase and collapse whitespace so statement descriptions compare consistently."""
    return " ".join(text.upper().split())


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
    if not in_range(rule, amount):
        return False
    text = normalize(description)
    pattern = normalize(rule.pattern)
    if rule.match_type == "contains":
        return pattern in text
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
