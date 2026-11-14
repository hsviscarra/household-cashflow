import {
  type CategoryUses,
  type Category,
  type CategoryGroup,
  fetchCategoryUses,
  deleteCategory,
} from "../../api";
import { type Notify, useSave, Swatch } from "./shared";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

/** "12 lines, 1 rule and 2 bills" */
export function usesText(u: CategoryUses): string {
  const part = (n: number, one: string, many = `${one}s`) => (n ? `${n} ${n === 1 ? one : many}` : "");
  const parts = [
    part(u.lines, "line"),
    part(u.rules, "rule"),
    part(u.bills, "bill"),
    part(u.budgets, "budget"),
    part(u.other, "other link", "other links"),
  ].filter(Boolean);
  return parts.length > 1
    ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`
    : (parts[0] ?? "nothing");
}

/** Delete a category (ADR-034): straight away when unused; otherwise its lines, rules and bills
 * move to another category of the same kind first. A group goes once it has no subcategories. */
export function DeleteCategory({
  category: c,
  subs,
  sameKind,
  notify,
}: {
  category: Category;
  subs: number;
  sameKind: CategoryGroup[];
  notify: Notify;
}) {
  const [asking, setAsking] = useState(false);
  const [moveTo, setMoveTo] = useState("");
  const uses = useQuery({
    queryKey: ["category-uses", c.category_id],
    queryFn: () => fetchCategoryUses(c.category_id),
    enabled: asking && !subs,
  });
  const remove = useSave(
    (to: number | null) => deleteCategory(c.category_id, to),
    [["categories"], ["rules"], ["review"], ["transactions"], ["cashflow"], ["spending"]],
    notify,
  );
  const targets = sameKind.flatMap((g) => [
    ...(g.category_id === c.category_id ? [] : [{ id: g.category_id, label: g.name }]),
    ...g.children
      .filter((x) => x.category_id !== c.category_id)
      .map((x) => ({ id: x.category_id, label: `${g.name} / ${x.name}` })),
  ]);
  if (!asking)
    return (
      <button type="button" className="btn btn-quiet mt-3 text-danger-ink" onClick={() => setAsking(true)}>
        Delete {c.name}…
      </button>
    );
  const u = uses.data;
  const go = (to: number | null) =>
    remove.mutate(to, {
      onSuccess: (moved) =>
        notify(
          moved.total
            ? `Deleted ${c.name}; ${usesText(moved)} moved to ${targets.find((t) => t.id === to)?.label}.`
            : `Deleted ${c.name}.`,
        ),
    });
  return (
    <div
      className="mt-3 rounded-xl border border-line bg-ground p-3 text-sm"
      role="group"
      aria-label={`Delete ${c.name}`}
    >
      {subs > 0 ? (
        <p>
          {c.name} has {subs} {subs === 1 ? "subcategory" : "subcategories"}: delete them, or move them to
          another group (Edit → In the group), first.
        </p>
      ) : !u ? (
        <p className="text-muted">Checking what uses {c.name}…</p>
      ) : u.total === 0 ? (
        <p>
          Nothing uses {c.name}.{" "}
          <button
            type="button"
            className="btn btn-secondary ml-2 h-9 px-3"
            disabled={remove.isPending}
            onClick={() => go(null)}
          >
            Delete it
          </button>
        </p>
      ) : (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (moveTo) go(Number(moveTo));
          }}
        >
          <p className="w-full">
            {c.name} is used by {usesText(u)}. They move to the category you choose, with each line’s change
            kept in its history, so no amount is lost.
          </p>
          <label className="min-w-56 flex-1">
            <span className="label">Move them to</span>
            <select className="field" required value={moveTo} onChange={(e) => setMoveTo(e.target.value)}>
              <option value="">Choose a category</option>
              {targets.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="btn btn-secondary" disabled={remove.isPending || !moveTo}>
            Move and delete
          </button>
        </form>
      )}
      <button type="button" className="btn btn-quiet mt-2 h-9 px-3" onClick={() => setAsking(false)}>
        Keep it
      </button>
    </div>
  );
}

export function SubcategoryAdd({
  group: g,
  busy,
  create,
  notify,
}: {
  group: CategoryGroup;
  busy: boolean;
  create: (b: { name: string; parent_id: number }, o: { onSuccess: () => void }) => void;
  notify: Notify;
}) {
  const [newChild, setNewChild] = useState("");
  return (
    <form
      className="mt-3 flex flex-wrap items-end gap-2 pl-6"
      onSubmit={(e) => {
        e.preventDefault();
        const name = newChild.trim();
        if (!name) return;
        create(
          { name, parent_id: g.category_id },
          {
            onSuccess: () => {
              setNewChild("");
              notify(`Subcategory added: ${g.name} / ${name}.`);
            },
          },
        );
      }}
    >
      <label className="min-w-48 flex-1">
        <span className="sr-only">New subcategory in {g.name}</span>
        <input
          className="field"
          placeholder={`New subcategory in ${g.name}`}
          maxLength={100}
          value={newChild}
          onChange={(e) => setNewChild(e.target.value)}
        />
      </label>
      <button type="submit" className="btn btn-secondary" disabled={busy}>
        Add subcategory
      </button>
    </form>
  );
}

/** "120 lines · 2 rules", or "Not used yet" (a candidate to hide). */
export function usage(lines: number, rules: number): string {
  if (!lines && !rules) return "Not used yet";
  const part = (n: number, one: string) => `${n.toLocaleString("en-US")} ${n === 1 ? one : `${one}s`}`;
  return [lines && part(lines, "line"), rules && part(rules, "rule")].filter(Boolean).join(" · ");
}

export function CategoryLine(props: {
  category: Category;
  heading?: boolean;
  total?: number;
  onEdit: () => void;
}) {
  const c = props.category;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {props.heading && <Swatch color={c.color} />}
          <span className={props.heading ? "text-lg font-semibold" : ""}>{c.name}</span>
          {c.is_fixed && <span className="pill bg-info-bg text-ink">Fixed</span>}
          {!c.is_active && <span className="pill pill-muted">Hidden</span>}
          <span className="text-sm text-muted">{usage(props.total ?? c.lines ?? 0, c.rules ?? 0)}</span>
        </div>
        <p className={`text-sm ${c.description ? "text-muted" : "italic text-muted"}`}>
          {c.description || "No description yet: Edit to say what goes here."}
        </p>
      </div>
      <button className="btn btn-quiet" onClick={props.onEdit} aria-label={`Edit ${c.name}`}>
        Edit
      </button>
    </div>
  );
}

export function CategoryForm(props: {
  category: Category;
  groups?: CategoryGroup[]; // a subcategory can move to one of these (same kind)
  withColor?: boolean;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: Partial<Category>) => void;
}) {
  const c = props.category;
  const [name, setName] = useState(c.name);
  const [color, setColor] = useState(c.color ?? "#6B6788");
  const [fixed, setFixed] = useState(c.is_fixed);
  const [active, setActive] = useState(c.is_active);
  const [about, setAbout] = useState(c.description ?? "");
  const [parent, setParent] = useState(c.parent_id);
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        props.onSubmit({
          name: name.trim(),
          is_fixed: fixed,
          is_active: active,
          description: about.trim() || null,
          ...(props.groups && parent !== c.parent_id ? { parent_id: parent } : {}),
          ...(props.withColor ? { color: color.toUpperCase() } : {}),
        });
      }}
    >
      <label className="min-w-48 flex-1">
        <span className="label">Name</span>
        <input
          className="field"
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      {props.groups && (
        <label className="min-w-48">
          <span className="label">In the group</span>
          <select className="field" value={parent ?? ""} onChange={(e) => setParent(Number(e.target.value))}>
            {props.groups.map((g) => (
              <option key={g.category_id} value={g.category_id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="w-full">
        <span className="label">What goes here</span>
        <textarea
          className="field h-auto min-h-20 py-2"
          maxLength={400}
          rows={2}
          placeholder="Shown when choosing a category, and Claude reads it when suggesting one."
          value={about}
          onChange={(e) => setAbout(e.target.value)}
        />
      </label>
      {props.withColor && (
        <label>
          <span className="label">Color</span>
          <input
            type="color"
            className="field w-20 p-1"
            value={color}
            onChange={(e) => setColor(e.target.value)}
          />
        </label>
      )}
      <label className="flex h-11 items-center gap-2">
        <input
          type="checkbox"
          className="h-5 w-5"
          checked={fixed}
          onChange={(e) => setFixed(e.target.checked)}
        />
        Fixed cost
      </label>
      <label className="flex h-11 items-center gap-2">
        <input
          type="checkbox"
          className="h-5 w-5"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
        />
        Active
      </label>
      <button type="submit" className="btn btn-primary" disabled={props.busy}>
        Save category
      </button>
      <button type="button" className="btn btn-quiet" onClick={props.onCancel}>
        Cancel
      </button>
    </form>
  );
}
