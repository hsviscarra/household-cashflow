import { type Notify, useSave, Loading, KIND_LABEL, Panel } from "./shared";
import { useQuery } from "@tanstack/react-query";
import {
  fetchCategories,
  createCategory,
  type CategoryKind,
  type Category,
  type CategoryGroup,
  updateCategory,
} from "../../api";
import { useState } from "react";
import { fold } from "../../components/CategoryPicker";
import { CategoryForm, DeleteCategory, CategoryLine, SubcategoryAdd } from "./CategoryParts";

// ---------------- categories ----------------
export function CategoriesTab({ notify }: { notify: Notify }) {
  const { data, error } = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Set<number>>(new Set());
  const create = useSave(createCategory, [["categories"]], notify);

  if (!data) return <Loading what="categories" error={error} />;
  const kinds = Object.keys(KIND_LABEL) as CategoryKind[];
  const words = fold(query.trim()).split(/\s+/).filter(Boolean);
  const hit = (c: Category) => words.every((w) => fold(`${c.name} ${c.description ?? ""}`).includes(w));
  // A group shows when it or one of its subcategories matches; a matching group shows them all.
  const shown = data
    .map((g) => ({ g, children: !words.length || hit(g) ? g.children : g.children.filter(hit) }))
    .filter(({ g, children }) => !words.length || hit(g) || children.length > 0);
  const toggle = (id: number) =>
    setOpen((was) => {
      const next = new Set(was);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="min-w-56 flex-1 md:max-w-sm">
          <span className="label">Find a category</span>
          <input
            className="field"
            type="search"
            placeholder="Name or what goes in it"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          {!words.length && (
            <button
              className="btn btn-quiet"
              onClick={() =>
                setOpen(open.size === data.length ? new Set() : new Set(data.map((g) => g.category_id)))
              }
            >
              {open.size === data.length ? "Collapse all" : "Expand all"}
            </button>
          )}
          {!adding && (
            <button className="btn btn-primary" onClick={() => setAdding(true)}>
              Add group
            </button>
          )}
        </div>
      </div>
      {words.length > 0 && (
        <p aria-live="polite" className="text-muted">
          {shown.length
            ? `${shown.length} ${shown.length === 1 ? "group matches" : "groups match"} “${query.trim()}”.`
            : `Nothing matches “${query.trim()}”.`}
        </p>
      )}
      {adding && (
        <Panel>
          <GroupForm
            busy={create.isPending}
            onCancel={() => setAdding(false)}
            onSubmit={(body) =>
              create.mutate(body, {
                onSuccess: () => {
                  setAdding(false);
                  notify(`Group added: ${body.name}.`);
                },
              })
            }
          />
        </Panel>
      )}
      {kinds.map((kind) => {
        const groups = shown.filter(({ g }) => g.kind === kind);
        if (!groups.length) return null;
        return (
          <div key={kind}>
            <h2 className="font-display text-2xl font-bold">{KIND_LABEL[kind]}</h2>
            <ul className="mt-3 space-y-3">
              {groups.map(({ g, children }) => (
                <li key={g.category_id}>
                  <GroupCard
                    group={g}
                    subs={children}
                    open={words.length > 0 || open.has(g.category_id)}
                    onToggle={() => toggle(g.category_id)}
                    sameKind={data.filter((x) => x.kind === g.kind)}
                    notify={notify}
                  />
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

export function GroupForm(props: {
  busy: boolean;
  onCancel: () => void;
  onSubmit: (b: { name: string; kind: CategoryKind; color: string }) => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<CategoryKind>("expense");
  const [color, setColor] = useState("#6B6788");
  return (
    <form
      className="grid gap-4 md:grid-cols-3"
      onSubmit={(e) => {
        e.preventDefault();
        props.onSubmit({ name: name.trim(), kind, color: color.toUpperCase() });
      }}
    >
      <label>
        <span className="label">Group name</span>
        <input
          className="field"
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        <span className="label">Counts as</span>
        <select className="field" value={kind} onChange={(e) => setKind(e.target.value as CategoryKind)}>
          {(Object.keys(KIND_LABEL) as CategoryKind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Color</span>
        <input type="color" className="field p-1" value={color} onChange={(e) => setColor(e.target.value)} />
      </label>
      <div className="flex gap-2 md:col-span-3">
        <button type="submit" className="btn btn-primary" disabled={props.busy}>
          Add group
        </button>
        <button type="button" className="btn btn-quiet" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function GroupCard({
  group: g,
  subs,
  open,
  onToggle,
  sameKind,
  notify,
}: {
  group: CategoryGroup;
  subs: Category[]; // the subcategories to show (search may hide some)
  open: boolean;
  onToggle: () => void;
  sameKind: CategoryGroup[]; // where a subcategory can move
  notify: Notify;
}) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const update = useSave(
    (a: { id: number; body: Partial<Category> }) => updateCategory(a.id, a.body),
    [["categories"], ["rules"]],
    notify,
  );
  const create = useSave(createCategory, [["categories"]], notify);

  const saveEdit = (c: Category, body: Partial<Category>) =>
    update.mutate(
      { id: c.category_id, body },
      {
        onSuccess: () => {
          setEditingId(null);
          const to = sameKind.find((x) => x.category_id === body.parent_id);
          notify(
            to && body.parent_id !== c.parent_id
              ? `Moved ${body.name ?? c.name} to ${to.name}; its lines and rules moved with it.`
              : `Category saved: ${body.name ?? c.name}.`,
          );
        },
      },
    );
  const lines = (g.lines ?? 0) + g.children.reduce((n, c) => n + (c.lines ?? 0), 0);
  const listId = `subcategories-${g.category_id}`;

  return (
    <Panel>
      {editingId === g.category_id ? (
        <>
          <CategoryForm
            category={g}
            withColor
            busy={update.isPending}
            onCancel={() => setEditingId(null)}
            onSubmit={(body) => saveEdit(g, body)}
          />
          <DeleteCategory category={g} subs={g.children.length} sameKind={sameKind} notify={notify} />
        </>
      ) : (
        <CategoryLine category={g} heading total={lines} onEdit={() => setEditingId(g.category_id)} />
      )}
      <button
        type="button"
        className="mt-2 text-sm font-semibold text-primary underline-offset-2 hover:underline"
        aria-expanded={open}
        aria-controls={listId}
        onClick={onToggle}
      >
        {open ? "▾" : "▸"} {g.children.length} {g.children.length === 1 ? "subcategory" : "subcategories"}
        <span className="sr-only"> in {g.name}</span>
      </button>
      {open && (
        <div id={listId}>
          <ul className="mt-3 divide-y divide-line border-t border-line">
            {subs.map((c) => (
              <li key={c.category_id} className="py-2 pl-6">
                {editingId === c.category_id ? (
                  <>
                    <CategoryForm
                      category={c}
                      groups={sameKind}
                      busy={update.isPending}
                      onCancel={() => setEditingId(null)}
                      onSubmit={(body) => saveEdit(c, body)}
                    />
                    <DeleteCategory category={c} subs={0} sameKind={sameKind} notify={notify} />
                  </>
                ) : (
                  <CategoryLine category={c} onEdit={() => setEditingId(c.category_id)} />
                )}
              </li>
            ))}
          </ul>
          <SubcategoryAdd group={g} busy={create.isPending} create={create.mutate} notify={notify} />
        </div>
      )}
    </Panel>
  );
}
