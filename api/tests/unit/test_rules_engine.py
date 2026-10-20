import pytest

from app.services.rules import Rule, first_match, matches, normalize, validate_pattern


def rule(pattern: str, match_type: str = "contains", priority: int = 50, rid: int = 1) -> Rule:
    return Rule(rid, pattern, match_type, category_id=1, priority=priority)


def test_normalize_uppercases_and_collapses_spaces() -> None:
    assert normalize("  uber   eats  San Jose ") == "UBER EATS SAN JOSE"


@pytest.mark.parametrize(
    ("pattern", "match_type", "text", "expected"),
    [
        ("UBER EATS", "contains", "UBER EATS SAN JOSE", True),
        ("uber eats", "contains", "Uber  Eats San Jose", True),
        ("GOOGLE *", "starts_with", "GOOGLE *Retake AI Face M", True),
        ("GOOGLE *", "starts_with", "PAY GOOGLE *X", False),
        (r"ZURITA\s+Y\s+ZURITA", "regex", "zurita y zurita laborator Quito", True),
        ("[unclosed", "regex", "anything", False),
        ("X", "unknown", "X", False),
    ],
)
def test_matches(pattern: str, match_type: str, text: str, expected: bool) -> None:
    assert matches(rule(pattern, match_type), text) is expected


def test_first_match_respects_priority_and_skips_inactive() -> None:
    rules = [
        rule("UBER", priority=50, rid=1),
        rule("UBER *ONE MEMBERSHIP", priority=10, rid=2),
        Rule(3, "UBER", "contains", 1, priority=1, is_active=False),
    ]
    hit = first_match(rules, "UBER *ONE MEMBERSHIP UBER.COM/BILL")
    assert hit is not None and hit.rule_id == 2
    hit = first_match(rules, "UBER RIDES SAN JOSE")
    assert hit is not None and hit.rule_id == 1
    assert first_match(rules, "SUPERMAXI") is None


def test_validate_pattern() -> None:
    assert validate_pattern("  ", "contains") is not None
    assert validate_pattern("(", "regex") is not None
    assert validate_pattern("SUPERMAXI", "contains") is None
