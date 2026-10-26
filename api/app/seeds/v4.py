"""Seed v4 (F9): rules that need an amount range. Frozen like the earlier seeds.

(pattern, match_type, "Group/Sub", priority, amount_min, amount_max) on the absolute amount.
"""

from decimal import Decimal

# Produbanco prints both IESS payments the same way; Hernan: split them by amount (F7).
MERCHANT_RULES: list[tuple[str, str, str, int, Decimal | None, Decimal | None]] = [
    ("PAGO IESS", "starts_with", "Household Staff/Empleada IESS", 5, None, Decimal("299.99")),
    ("PAGO IESS", "starts_with", "Housing/Mortgage BIESS", 5, Decimal("300"), None),
]
