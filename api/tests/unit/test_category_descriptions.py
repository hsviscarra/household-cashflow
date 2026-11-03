"""F23: category descriptions and usage counts."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category
from app.seeds import _category_ids, load_v5, v5


def test_every_seeded_category_is_described(db: Session) -> None:
    ids = _category_ids(db.connection(), Category.__table__)
    assert set(v5.DESCRIPTIONS) == set(ids), set(v5.DESCRIPTIONS) ^ set(ids)
    assert all(0 < len(text) <= 400 for text in v5.DESCRIPTIONS.values())
    assert all(c.description for c in db.scalars(select(Category)))


def test_loading_again_keeps_edited_descriptions(db: Session) -> None:
    rent = db.scalar(select(Category).where(Category.name == "Office Rent"))
    assert rent is not None
    rent.description = "Edited by Hernan."
    db.commit()
    assert load_v5(db.connection(), Category.__table__) == 0
    db.refresh(rent)
    assert rent.description == "Edited by Hernan."


def _find(groups: list[dict], path: str) -> dict:  # type: ignore[type-arg]
    group, _, sub = path.partition("/")
    g = next(x for x in groups if x["name"] == group)
    return g if not sub else next(c for c in g["children"] if c["name"] == sub)  # type: ignore[no-any-return]


def test_categories_list_descriptions_and_how_often_they_are_used(client: TestClient) -> None:
    groups = client.get("/api/categories").json()
    visa = _find(groups, "Groceries/Supermarket")
    assert visa["description"].startswith("Supermaxi")
    assert visa["rules"] >= 1 and visa["lines"] == 0  # seeded rules; nothing loaded yet

    created = client.post(
        "/api/categories",
        json={
            "name": "Pet Food",
            "parent_id": _find(groups, "Pets")["category_id"],
            "description": "Food and treats for the pets.",
        },
    ).json()
    assert created["description"] == "Food and treats for the pets."
    edited = client.patch(
        f"/api/categories/{created['category_id']}", json={"description": "Food and treats."}
    ).json()
    assert edited["description"] == "Food and treats."
    too_long = client.patch(
        f"/api/categories/{created['category_id']}", json={"description": "x" * 401}
    )
    assert too_long.status_code == 422
    cleared = client.patch(f"/api/categories/{created['category_id']}", json={"description": None})
    assert cleared.json()["description"] is None


def test_lines_are_counted_once_loaded(client: TestClient) -> None:
    from tests.fixtures import statements as s

    up = client.post(
        "/api/statements", files=[("files", ("c.pdf", s.capitalone_full(), "application/pdf"))]
    )
    st = up.json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    client.post(f"/api/batches/{b['batch_id']}/approve")
    used = [
        c for g in client.get("/api/categories").json() for c in [g, *g["children"]] if c["lines"]
    ]
    assert used and sum(c["lines"] for c in used) == sum(
        1 for ln in b["lines"] if ln["category_id"] and not ln["is_duplicate"]
    )
