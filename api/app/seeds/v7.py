"""Seed v7: the fuller category tree Hernan approved on Nov 5, 2026, drafted from the July to
October 2026 statements and the workbook rows. Frozen like the earlier seeds: change seeds with a
new version, never by editing this one. Every step skips what Hernan already renamed, moved or
added in Settings, so the migration never undoes his edits.
"""

# Renamed seeded categories: ("Group" or "Group/Sub", new name).
RENAMES: list[tuple[str, str]] = [
    ("Travel", "Travel & Vacations"),
]

# New groups: (group, kind, color, [(subcategory, is_fixed)]).
NEW_GROUPS: list[tuple[str, str, str, list[tuple[str, bool]]]] = [
    (
        "Insurance",
        "expense",
        "#0F766E",
        [("Car Insurance", True), ("Home Insurance", True), ("Life Insurance", True)],
    ),
    (
        "Entertainment & Leisure",
        "expense",
        "#D946EF",
        [
            ("Sports & Clubs", False),
            ("Gym & Fitness", False),
            ("Outings & Events", False),
            ("Hobbies & Games", False),
        ],
    ),
    (
        "Education & Career",
        "expense",
        "#4338CA",
        [("Courses & Certifications", False), ("Books", False), ("Job Search", False)],
    ),
    ("Personal Care", "expense", "#DB2777", [("Hair & Beauty", False), ("Spa & Massage", False)]),
    (
        "Gifts & Celebrations",
        "expense",
        "#EA580C",
        [("Gifts", False), ("Parties & Holidays", False)],
    ),
    ("Family Support", "expense", "#65A30D", [("Money to Family", False)]),
    ("Taxes", "expense", "#57534E", [("Income Tax", False), ("Property Tax", True)]),
]

# Seeded subcategories that move to a new group, renamed on the way:
# ("Group/Sub" today, new group, new name).
MOVES: list[tuple[str, str, str]] = [
    ("Health/Insurance", "Insurance", "Health Insurance"),
    ("Health/Dad's Insurance", "Insurance", "Dad's Health Insurance"),
]

# New subcategories in existing groups: (group, [(subcategory, is_fixed)]).
NEW_SUBS: list[tuple[str, list[tuple[str, bool]]]] = [
    (
        "Travel & Vacations",
        [
            ("Lodging", False),
            ("Flights", False),
            ("Trip Transport", False),
            ("Trip Activities & Food", False),
        ],
    ),
    ("Health", [("Hospital", False), ("Dental", False)]),
    ("Transport", [("Car Maintenance", False), ("Tolls", False)]),
    ("Pets", [("Vet", False), ("Pet Food & Supplies", False)]),
    ("Shopping", [("Home & Furniture", False)]),
    (
        "Other Income",
        [
            ("Consulting & Freelance", False),
            ("Gifts Received", False),
            ("Reimbursements from Others", False),
        ],
    ),
    # Transfers: none of these counts as income or spending, and none has a leg in another of
    # the household's accounts, so Data Status doesn't ask for "the other side".
    (
        "Transfers",
        [("Held for Others", False), ("Loans to Others", False), ("Loan Repaid to Me", False)],
    ),
]

DESCRIPTIONS: dict[str, str] = {
    "Insurance": "Insurance premiums: health, car, home and life. Claims paid back are income.",
    "Insurance/Health Insurance": "The family's health plan, e.g. Ecuasanitas or BMI installments.",
    "Insurance/Dad's Health Insurance": "The health insurance you pay for your dad (H&C).",
    "Insurance/Car Insurance": "The car's insurance policy, e.g. AIG Pay Club Express.",
    "Insurance/Home Insurance": "Insurance on the house or the office, e.g. Zurich.",
    "Insurance/Life Insurance": "Life insurance premiums.",
    "Entertainment & Leisure": "Free time: clubs, sports, the gym, outings, hobbies.",
    "Entertainment & Leisure/Sports & Clubs": "Club fees and sports, e.g. Quito Tenis y Golf.",
    "Entertainment & Leisure/Gym & Fitness": "Gym classes and fitness apps, e.g. Workout, Fitbod.",
    "Entertainment & Leisure/Outings & Events": "Cinema, concerts, museums, parks, tickets.",
    "Entertainment & Leisure/Hobbies & Games": "Hobby supplies, games, toys for grown-ups.",
    "Travel & Vacations": "Trips away from home. Daily dining and shopping stay in their groups.",
    "Travel & Vacations/Lodging": "Hotels, lodges, Airbnb.",
    "Travel & Vacations/Flights": "Airline tickets and baggage fees.",
    "Travel & Vacations/Trip Transport": "Rental cars, buses, taxis and fuel on a trip.",
    "Travel & Vacations/Trip Activities & Food": "Tours, entrance fees and meals while on a trip.",
    "Education & Career": "Learning and work: courses, exams, books, job search.",
    "Education & Career/Courses & Certifications": "Courses and exams, e.g. Kryterion.",
    "Education & Career/Books": "Books and e-books.",
    "Education & Career/Job Search": "Job boards and services, e.g. FlexJobs.",
    "Personal Care": "Haircuts, beauty and wellness services.",
    "Personal Care/Hair & Beauty": "Haircuts, salons, barbers, cosmetics.",
    "Personal Care/Spa & Massage": "Spa days and massages.",
    "Gifts & Celebrations": "Presents and parties.",
    "Gifts & Celebrations/Gifts": "Presents for others: birthdays, Christmas, weddings.",
    "Gifts & Celebrations/Parties & Holidays": "Birthday parties, Christmas dinners, celebrations.",
    "Family Support": "Money you give family members to help them, not to be paid back.",
    "Family Support/Money to Family": "Help given to parents or relatives. Loans go to Transfers.",
    "Taxes": "Taxes you pay directly. Taxes on purchases stay in the purchase.",
    "Taxes/Income Tax": "Income tax payments and balances due: SRI, IRS.",
    "Taxes/Property Tax": "The predial on the house and the office.",
    "Health/Hospital": "Hospital and clinic bills, e.g. Hospital de los Valles.",
    "Health/Dental": "Dentists and orthodontists.",
    "Transport/Car Maintenance": "Service, tires, repairs and car wash.",
    "Transport/Tolls": "Road tolls (peajes).",
    "Pets/Vet": "Vet visits and pet medicine.",
    "Pets/Pet Food & Supplies": "Pet food, toys and supplies.",
    "Shopping/Home & Furniture": "Furniture, home goods and hardware, e.g. Kywi.",
    "Other Income/Consulting & Freelance": "Paid side work and consulting.",
    "Other Income/Gifts Received": "Money given to you as a gift.",
    "Other Income/Reimbursements from Others": (
        "People paying you back for something you covered for them. Not insurance claims."
    ),
    "Transfers/Held for Others": (
        "Money that passes through your accounts but belongs to someone else: what you receive "
        "for them and what you send on or pay for them. Not income, not spending."
    ),
    "Transfers/Loans to Others": "Money you lend that should come back.",
    "Transfers/Loan Repaid to Me": "Money coming back from a loan you gave.",
}

# Seeded rules that now point to a new category: (pattern, "Group/Sub" today, "Group/Sub" new).
RULE_MOVES: list[tuple[str, str, str]] = [
    ("FLEXJOBS", "Subscriptions & Software/Professional", "Education & Career/Job Search"),
]

# (pattern, match_type, "Group/Sub", priority), for merchants seen in July to October 2026.
MERCHANT_RULES: list[tuple[str, str, str, int]] = [
    ("QUITO TENIS Y GOLF", "contains", "Entertainment & Leisure/Sports & Clubs", 20),
    ("WORKOUT QUITO", "contains", "Entertainment & Leisure/Gym & Fitness", 20),
    ("FITBOD", "contains", "Entertainment & Leisure/Gym & Fitness", 20),
    ("ZURICH ECUADOR", "contains", "Insurance/Home Insurance", 15),
    ("AIG PAY CLUB", "contains", "Insurance/Car Insurance", 15),
    ("HOSP DE LOS VALLES", "contains", "Health/Hospital", 20),
    ("LAB ECUA AMERICAN", "contains", "Health/Labs & Imaging", 20),
    ("KRYTERION", "contains", "Education & Career/Courses & Certifications", 20),
    ("LODGE", "contains", "Travel & Vacations/Lodging", 30),
    ("HOTEL", "starts_with", "Travel & Vacations/Lodging", 30),
    ("AIRBNB", "contains", "Travel & Vacations/Lodging", 20),
    ("MEGAKYWI", "contains", "Shopping/Home & Furniture", 20),
]
