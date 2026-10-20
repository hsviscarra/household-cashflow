"""Seed loaders shared by migrations and tests."""

from typing import Any

from sqlalchemy import Connection, Table, delete, func, insert, select

from app.seeds import v1, v2


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


def load_v2(conn: Connection, category: Table) -> None:
    """Add the seed v2 categories; existing groups get new subcategories, new groups are created."""
    for group, kind, color, children in v2.CATEGORIES:
        gid = conn.execute(
            select(category.c.category_id).where(
                category.c.parent_id.is_(None), category.c.name == group
            )
        ).scalar_one_or_none()
        if gid is None:
            order = conn.execute(
                select(func.count()).select_from(category).where(category.c.parent_id.is_(None))
            ).scalar_one()
            gid = conn.execute(
                insert(category).returning(category.c.category_id),
                {
                    "parent_id": None,
                    "name": group,
                    "kind": kind,
                    "color": color,
                    "is_fixed": False,
                    "sort_order": order,
                },
            ).scalar_one()
        start = conn.execute(
            select(func.count()).select_from(category).where(category.c.parent_id == gid)
        ).scalar_one()
        if children:
            conn.execute(
                insert(category),
                [
                    {
                        "parent_id": gid,
                        "name": name,
                        "kind": kind,
                        "color": None,
                        "is_fixed": fixed,
                        "sort_order": start + i,
                    }
                    for i, (name, fixed) in enumerate(children)
                ],
            )


def unload_v2(conn: Connection, category: Table) -> None:
    """Remove what load_v2 added (subcategories first, then the groups it created)."""
    for group, _kind, color, children in v2.CATEGORIES:
        gid = conn.execute(
            select(category.c.category_id).where(
                category.c.parent_id.is_(None), category.c.name == group
            )
        ).scalar_one_or_none()
        if gid is None:
            continue
        names = [n for n, _ in children]
        if names:
            conn.execute(
                delete(category).where(category.c.parent_id == gid, category.c.name.in_(names))
            )
        if color is not None:
            conn.execute(delete(category).where(category.c.category_id == gid))
