"""Merchant rule matching: the first active rule (lowest priority number) that matches wins.

Used by the Settings page rule tester now and by classification during imports (F9).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    rule_id: int
    pattern: str
    match_type: str
    category_id: int
    priority: int
    is_active: bool = True


def normalize(text: str) -> str:
    """Uppercase and collapse whitespace so statement descriptions compare consistently."""
    return " ".join(text.upper().split())


def matches(rule: Rule, description: str) -> bool:
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


def first_match(rules: Iterable[Rule], description: str) -> Rule | None:
    for rule in sorted(rules, key=lambda r: (r.priority, r.rule_id)):
        if rule.is_active and matches(rule, description):
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
