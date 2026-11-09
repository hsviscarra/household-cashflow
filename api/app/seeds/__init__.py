"""Seed loaders shared by migrations and tests."""

from typing import Any

from sqlalchemy import Connection, Table, delete, func, insert, select, update

from app.seeds import v1, v2, v3, v4, v5, v6, v7


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


def _category_ids(conn: Connection, category: Table) -> dict[str, int]:
    rows = list(conn.execute(select(category.c.category_id, category.c.name, category.c.parent_id)))
    names = {r.category_id: r.name for r in rows}
    return {
        (f"{names[r.parent_id]}/{r.name}" if r.parent_id is not None else r.name): r.category_id
        for r in rows
    }


def load_v3(conn: Connection, account: Table, category: Table, merchant_rule: Table) -> None:
    """Add the Pacificard account and its merchant rules."""
    conn.execute(insert(account), [dict(a) for a in v3.ACCOUNTS])
    ids = _category_ids(conn, category)
    conn.execute(
        insert(merchant_rule),
        [
            {"pattern": p, "match_type": m, "category_id": ids[path], "priority": prio}
            for p, m, path, prio in v3.MERCHANT_RULES
        ],
    )


def unload_v3(conn: Connection, account: Table, merchant_rule: Table) -> None:
    conn.execute(
        delete(merchant_rule).where(merchant_rule.c.pattern.in_([p for p, *_ in v3.MERCHANT_RULES]))
    )
    conn.execute(delete(account).where(account.c.name.in_([a["name"] for a in v3.ACCOUNTS])))


def load_v4(conn: Connection, category: Table, merchant_rule: Table) -> None:
    """Add the amount-range rules (F9)."""
    ids = _category_ids(conn, category)
    conn.execute(
        insert(merchant_rule),
        [
            {
                "pattern": p,
                "match_type": m,
                "category_id": ids[path],
                "priority": prio,
                "amount_min": lo,
                "amount_max": hi,
            }
            for p, m, path, prio, lo, hi in v4.MERCHANT_RULES
        ],
    )


def unload_v4(conn: Connection, merchant_rule: Table) -> None:
    conn.execute(
        delete(merchant_rule).where(
            merchant_rule.c.pattern.in_({p for p, *_ in v4.MERCHANT_RULES}),
            (merchant_rule.c.amount_min.is_not(None)) | (merchant_rule.c.amount_max.is_not(None)),
        )
    )


def load_v5(conn: Connection, category: Table) -> int:
    """Describe the seeded categories that have no description yet. Returns how many."""
    ids = _category_ids(conn, category)
    count = 0
    for path, text in v5.DESCRIPTIONS.items():
        if path not in ids:  # renamed or removed in the app: left for Hernan
            continue
        done = conn.execute(
            update(category)
            .where(category.c.category_id == ids[path], category.c.description.is_(None))
            .values(description=text)
        )
        count += done.rowcount or 0
    return count


def load_v6(conn: Connection, account: Table, category: Table, merchant_rule: Table) -> None:
    """Add the Produbanco Visa and its rule, unless Hernan already added them in Settings."""
    for a in v6.ACCOUNTS:
        taken = conn.execute(
            select(account.c.account_id).where(
                account.c.institution == a["institution"], account.c.last4 == a["last4"]
            )
        ).first()
        if taken is None:
            conn.execute(insert(account), [dict(a)])
    ids = _category_ids(conn, category)
    for p, m, path, prio in v6.MERCHANT_RULES:
        if conn.execute(
            select(merchant_rule.c.rule_id).where(merchant_rule.c.pattern == p)
        ).first():
            continue
        conn.execute(
            insert(merchant_rule),
            [{"pattern": p, "match_type": m, "category_id": ids[path], "priority": prio}],
        )


def unload_v6(conn: Connection, account: Table, merchant_rule: Table) -> None:
    conn.execute(
        delete(merchant_rule).where(merchant_rule.c.pattern.in_([p for p, *_ in v6.MERCHANT_RULES]))
    )
    conn.execute(delete(account).where(account.c.name.in_([a["name"] for a in v6.ACCOUNTS])))


def _group_id(conn: Connection, category: Table, name: str) -> int | None:
    return conn.execute(
        select(category.c.category_id).where(
            category.c.parent_id.is_(None), category.c.name == name
        )
    ).scalar_one_or_none()


def _child_count(conn: Connection, category: Table, parent_id: int | None) -> int:
    where = (
        category.c.parent_id.is_(None) if parent_id is None else category.c.parent_id == parent_id
    )
    return int(conn.execute(select(func.count()).select_from(category).where(where)).scalar_one())


def _add_subs(
    conn: Connection, category: Table, gid: int, kind: str, subs: list[tuple[str, bool]]
) -> None:
    taken = set(conn.scalars(select(category.c.name).where(category.c.parent_id == gid)))
    start = _child_count(conn, category, gid)
    rows = [
        {
            "parent_id": gid,
            "name": name,
            "kind": kind,
            "color": None,
            "is_fixed": fixed,
            "sort_order": start + i,
        }
        for i, (name, fixed) in enumerate(n for n in subs if n[0] not in taken)
    ]
    if rows:
        conn.execute(insert(category), rows)


def load_v7(conn: Connection, category: Table, merchant_rule: Table) -> None:
    """The fuller tree (seed v7). Anything Hernan already renamed, moved or added is left alone."""
    for path, new in v7.RENAMES:
        cid = _category_ids(conn, category).get(path)
        if cid is not None and new not in _category_ids(conn, category):
            conn.execute(update(category).where(category.c.category_id == cid).values(name=new))
    for group, kind, color, subs in v7.NEW_GROUPS:
        gid = _group_id(conn, category, group)
        if gid is None:
            gid = conn.execute(
                insert(category).returning(category.c.category_id),
                {
                    "parent_id": None,
                    "name": group,
                    "kind": kind,
                    "color": color,
                    "is_fixed": False,
                    "sort_order": _child_count(conn, category, None),
                },
            ).scalar_one()
        _add_subs(conn, category, gid, kind, subs)
    for path, group, new in v7.MOVES:
        ids = _category_ids(conn, category)
        gid = _group_id(conn, category, group)
        if path not in ids or gid is None or f"{group}/{new}" in ids:
            continue
        conn.execute(
            update(category)
            .where(category.c.category_id == ids[path])
            .values(parent_id=gid, name=new, sort_order=_child_count(conn, category, gid))
        )
    for group, subs in v7.NEW_SUBS:
        row = conn.execute(
            select(category.c.category_id, category.c.kind).where(
                category.c.parent_id.is_(None), category.c.name == group
            )
        ).first()
        if row is not None:
            _add_subs(conn, category, row.category_id, row.kind, subs)
    ids = _category_ids(conn, category)
    for path, text in v7.DESCRIPTIONS.items():
        if path in ids:
            conn.execute(
                update(category)
                .where(category.c.category_id == ids[path], category.c.description.is_(None))
                .values(description=text)
            )
    for pattern, old, new in v7.RULE_MOVES:
        if old in ids and new in ids:
            conn.execute(
                update(merchant_rule)
                .where(merchant_rule.c.pattern == pattern, merchant_rule.c.category_id == ids[old])
                .values(category_id=ids[new])
            )
    taken = set(conn.scalars(select(merchant_rule.c.pattern)))
    rows = [
        {"pattern": p, "match_type": m, "category_id": ids[path], "priority": prio}
        for p, m, path, prio in v7.MERCHANT_RULES
        if p not in taken and path in ids
    ]
    if rows:
        conn.execute(insert(merchant_rule), rows)


def v7_added(conn: Connection, category: Table) -> list[int]:
    """The ids of the subcategories and groups seed v7 created that still carry their names."""
    ids = _category_ids(conn, category)
    paths = [f"{g}/{n}" for g, _k, _c, subs in v7.NEW_GROUPS for n, _ in subs]
    paths += [f"{g}/{n}" for g, subs in v7.NEW_SUBS for n, _ in subs]
    paths += [g for g, *_ in v7.NEW_GROUPS]
    return [ids[p] for p in paths if p in ids]


def unload_v7(conn: Connection, category: Table, merchant_rule: Table) -> None:
    """Undo load_v7. The migration checks first that nothing uses the categories it removes."""
    ids = _category_ids(conn, category)
    conn.execute(
        delete(merchant_rule).where(merchant_rule.c.pattern.in_([p for p, *_ in v7.MERCHANT_RULES]))
    )
    for pattern, old, new in v7.RULE_MOVES:
        if old in ids and new in ids:
            conn.execute(
                update(merchant_rule)
                .where(merchant_rule.c.pattern == pattern, merchant_rule.c.category_id == ids[new])
                .values(category_id=ids[old])
            )
    for path, group, new in v7.MOVES:
        old_group, old_name = path.split("/", 1)
        gid = _group_id(conn, category, old_group)
        cid = ids.get(f"{group}/{new}")
        if gid is not None and cid is not None:
            conn.execute(
                update(category)
                .where(category.c.category_id == cid)
                .values(parent_id=gid, name=old_name)
            )
    added = v7_added(conn, category)
    groups = set(conn.scalars(select(category.c.category_id).where(category.c.parent_id.is_(None))))
    subs = [c for c in added if c not in groups]
    if subs:
        conn.execute(delete(category).where(category.c.category_id.in_(subs)))
    tops = [c for c in added if c in groups]
    if tops:
        conn.execute(delete(category).where(category.c.category_id.in_(tops)))
    for path, new in v7.RENAMES:
        cid = _category_ids(conn, category).get(new)
        if cid is not None:
            conn.execute(update(category).where(category.c.category_id == cid).values(name=path))


DEBT_CATEGORIES = ("Savings & Debt/Loan Payments", "Housing/Mortgage BIESS")


def load_v8(conn: Connection, category: Table) -> None:
    """Debt payment categories (ADR-054, migration 0038 does the same on the database, plus the
    categories loans and purchases are paid through)."""
    ids = _category_ids(conn, category)
    for path in DEBT_CATEGORIES:
        if path in ids:
            conn.execute(
                update(category).where(category.c.category_id == ids[path]).values(kind="debt")
            )


EXCHANGE = ("Transfers", "Exchange through people")


def load_v9(conn: Connection, category: Table) -> None:
    """Transfers / Exchange through people (ADR-055): paying someone in the US who pays the same
    in Ecuador (or the other way round). Migration 0039 adds it on the database."""
    gid = _group_id(conn, category, EXCHANGE[0])
    if gid is None:
        return
    _add_subs(conn, category, gid, "transfer", [(EXCHANGE[1], False)])
    if "description" in category.c:
        conn.execute(
            update(category)
            .where(category.c.parent_id == gid, category.c.name == EXCHANGE[1])
            .values(
                description="Paying someone in one country who pays you the same in the other "
                "(US and Ecuador). Not income or spending."
            )
        )


NEW_HOUSE = ("Housing", "New house")
# The developer's trust collects the new house's reserva, entrada and installments (ADR-056).
NEW_HOUSE_RULE = "KALANI"


def load_v10(conn: Connection, category: Table, merchant_rule: Table) -> None:
    """Housing / New house (ADR-056): the down payment being paid off before delivery, a debt
    payment. Its rule sends the developer's trust payments there. Migration 0040 adds both."""
    gid = _group_id(conn, category, NEW_HOUSE[0])
    if gid is None:
        return
    _add_subs(conn, category, gid, "debt", [(NEW_HOUSE[1], True)])
    if "description" in category.c:
        conn.execute(
            update(category)
            .where(category.c.parent_id == gid, category.c.name == NEW_HOUSE[1])
            .values(
                description="The new house's reserva, down payment and monthly installments "
                "before delivery. A debt payment, not spending."
            )
        )
    cid = _category_ids(conn, category).get("/".join(NEW_HOUSE))
    taken = set(conn.scalars(select(merchant_rule.c.pattern)))
    if cid is not None and NEW_HOUSE_RULE not in taken:
        conn.execute(
            insert(merchant_rule),
            [
                {
                    "pattern": NEW_HOUSE_RULE,
                    "match_type": "contains",
                    "category_id": cid,
                    "priority": 10,
                }
            ],
        )
