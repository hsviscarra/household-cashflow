"""Seed v6: Hernan's Produbanco Visa (card ending 5997) and a rule for its usual charge.
Frozen like the earlier seeds: change seeds with a new version, never by editing this one.
"""

ACCOUNTS: list[dict[str, str | None]] = [
    {
        "name": "Produbanco Visa",
        "institution": "Produbanco",
        "kind": "credit_card",
        "owner": "Hernan",
        "country": "EC",
        "last4": "5997",
    },
]

# (pattern, match_type, "Group/Sub", priority). Megadatos is Netlife, the home internet.
MERCHANT_RULES: list[tuple[str, str, str, int]] = [
    ("MEGADATOS", "contains", "Utilities/Phone/Internet", 20),
]
