"""Seed loaders shared by migrations and tests."""

from typing import Any

from sqlalchemy import Connection, Table, insert, select

from app.seeds import v1


def load_v1(
    conn: Connection, account: Table, category: Table, merchant_rule: Table
) -> dict[str, int]:
    """Insert seed v1 into empty reference tables. Returns {"Group/Sub" or "Group": category_id}."""
    conn.execute(insert(account), [dict(a) for a in v1.ACCOUNTS])

    ids: dict[str, int] = {}
    for order, group in enumerate(v1.CATEGORIES):
        gid = conn.execute(
            insert(category).returning(category.c.category_id),
            {
                "parent_id": None,
                "name": group["name"],
                "kind": group["kind"],
                "color": group["color"],
                "is_fixed": group["fixed"],
                "sort_order": order,
            },
        ).scalar_one()
        ids[group["name"]] = gid
        children: list[dict[str, Any]] = [
            {
                "parent_id": gid,
                "name": name,
                "kind": group["kind"],
                "color": None,
                "is_fixed": fixed,
                "sort_order": i,
            }
            for i, (name, fixed) in enumerate(group["children"])
        ]
        if children:
            conn.execute(insert(category), children)
            for row in conn.execute(
                select(category.c.category_id, category.c.name).where(category.c.parent_id == gid)
            ):
                ids[f"{group['name']}/{row.name}"] = row.category_id

    conn.execute(
        insert(merchant_rule),
        [
            {"pattern": p, "match_type": m, "category_id": ids[path], "priority": prio}
            for p, m, path, prio in v1.MERCHANT_RULES
        ],
    )
    return ids
