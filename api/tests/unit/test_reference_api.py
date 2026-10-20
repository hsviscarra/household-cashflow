from fastapi.testclient import TestClient

from app.seeds import v1, v2


# ---------- accounts ----------
def test_seeded_accounts_listed_with_last4_only(client: TestClient) -> None:
    accounts = client.get("/api/accounts").json()
    assert len(accounts) == len(v1.ACCOUNTS)
    capital_one = next(a for a in accounts if a["name"] == "Capital One Venture")
    assert capital_one["last4"] == "4003"
    assert all(a["last4"] is None or len(a["last4"]) == 4 for a in accounts)


def test_create_update_account(client: TestClient) -> None:
    body = {
        "name": "Interactive Brokers",
        "institution": "Interactive Brokers",
        "kind": "savings",
        "owner": "Hernan",
        "country": "US",
    }
    created = client.post("/api/accounts", json=body)
    assert created.status_code == 201
    aid = created.json()["account_id"]
    updated = client.patch(f"/api/accounts/{aid}", json={"is_active": False, "last4": "1234"})
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False
    assert updated.json()["last4"] == "1234"


def test_account_rejects_duplicates_and_full_numbers(client: TestClient) -> None:
    dup = {
        "name": "BofA Adv Plus Banking",
        "institution": "Bank of America",
        "kind": "checking",
        "owner": "Joint",
        "country": "US",
    }
    assert client.post("/api/accounts", json=dup).status_code == 409
    full = {**dup, "name": "New", "last4": "4460303388"}
    assert client.post("/api/accounts", json=full).status_code == 422


def test_update_missing_account_is_404(client: TestClient) -> None:
    assert client.patch("/api/accounts/9999", json={"name": "x"}).status_code == 404


# ---------- categories ----------
def test_categories_returned_as_groups_with_children(client: TestClient) -> None:
    groups = client.get("/api/categories").json()
    new_groups = [g for g, _kind, color, _children in v2.CATEGORIES if color is not None]
    assert [g["name"] for g in groups] == [g["name"] for g in v1.CATEGORIES] + new_groups
    housing = next(g for g in groups if g["name"] == "Housing")
    assert housing["kind"] == "expense"
    assert housing["color"] == "#6B6788"
    names = {c["name"]: c for c in housing["children"]}
    assert names["Condo Fee"]["is_fixed"] is True
    assert names["Home Maintenance"]["is_fixed"] is False


def test_create_subcategory_inherits_kind(client: TestClient) -> None:
    groups = client.get("/api/categories").json()
    travel = next(g for g in groups if g["name"] == "Travel")
    resp = client.post(
        "/api/categories", json={"name": "Flights", "parent_id": travel["category_id"]}
    )
    assert resp.status_code == 201
    assert resp.json()["kind"] == "expense"
    again = client.post(
        "/api/categories", json={"name": "Flights", "parent_id": travel["category_id"]}
    )
    assert again.status_code == 409


def test_create_group_needs_kind_and_only_two_levels(client: TestClient) -> None:
    assert client.post("/api/categories", json={"name": "Pets"}).status_code == 422
    pets = client.post(
        "/api/categories", json={"name": "Pets", "kind": "expense", "color": "#123456"}
    )
    assert pets.status_code == 201
    food = client.post(
        "/api/categories", json={"name": "Pet food", "parent_id": pets.json()["category_id"]}
    )
    assert food.status_code == 201
    deeper = client.post(
        "/api/categories", json={"name": "Treats", "parent_id": food.json()["category_id"]}
    )
    assert deeper.status_code == 422


def test_update_category_color_and_reject_bad_color(client: TestClient) -> None:
    group = client.get("/api/categories").json()[0]
    cid = group["category_id"]
    assert client.patch(f"/api/categories/{cid}", json={"color": "#000000"}).status_code == 200
    assert client.patch(f"/api/categories/{cid}", json={"color": "red"}).status_code == 422


# ---------- merchant rules ----------
def test_rules_listed_in_priority_order_with_paths(client: TestClient) -> None:
    rules = client.get("/api/merchant-rules").json()
    assert len(rules) == len(v1.MERCHANT_RULES)
    priorities = [r["priority"] for r in rules]
    assert priorities == sorted(priorities)
    uber_eats = next(r for r in rules if r["pattern"] == "UBER EATS")
    assert uber_eats["category_path"] == "Dining / Food Delivery"


def test_rule_tester_uses_seeded_rules(client: TestClient) -> None:
    def hit(desc: str) -> str | None:
        rule = client.get("/api/merchant-rules/test", params={"description": desc}).json()["rule"]
        return rule["category_path"] if rule else None

    assert hit("UBER *ONE MEMBERSHIP UBER.COM/BILL") == "Subscriptions & Software / Memberships"
    assert hit("UBER EATS SAN JOSE") == "Dining / Food Delivery"
    assert hit("SUPERMAXI EL JARDIN QUITO") == "Groceries / Supermarket"
    assert hit("GOOGLE *Retake AI Face M") == "Subscriptions & Software / Apps"
    assert hit("GOOGLE *YouTubeA M") == "Subscriptions & Software / Media"
    assert hit('SU PAGO "MUCHAS GRACIAS"') == "Transfers / Card Payment"
    assert hit("Transfer Kenility LLC Via WISE") == "Salary / Hernan"
    assert hit("Pay*MAURICIO FLORES Quito") is None


def test_create_update_delete_rule(client: TestClient) -> None:
    groups = client.get("/api/categories").json()
    services = next(g for g in groups if g["name"] == "Housing")
    created = client.post(
        "/api/merchant-rules",
        json={
            "pattern": "  MAURICIO FLORES ",
            "category_id": services["category_id"],
            "priority": 15,
        },
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["pattern"] == "MAURICIO FLORES"
    assert rule["category_path"] == "Housing"

    patched = client.patch(f"/api/merchant-rules/{rule['rule_id']}", json={"is_active": False})
    assert patched.json()["is_active"] is False
    test = client.get("/api/merchant-rules/test", params={"description": "Pay*MAURICIO FLORES"})
    assert test.json()["rule"] is None

    assert client.delete(f"/api/merchant-rules/{rule['rule_id']}").status_code == 204
    assert client.delete(f"/api/merchant-rules/{rule['rule_id']}").status_code == 404


def test_rule_validation(client: TestClient) -> None:
    bad_regex = {"pattern": "(", "match_type": "regex", "category_id": 1}
    assert client.post("/api/merchant-rules", json=bad_regex).status_code == 422
    no_category = {"pattern": "X", "category_id": 99999}
    assert client.post("/api/merchant-rules", json=no_category).status_code == 404
    first = client.get("/api/merchant-rules").json()[0]
    bad = client.patch(
        f"/api/merchant-rules/{first['rule_id']}", json={"pattern": "(", "match_type": "regex"}
    )
    assert bad.status_code == 422
