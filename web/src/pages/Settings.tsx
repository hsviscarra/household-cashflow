import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import {
  createAccount,
  createCategory,
  createRule,
  deleteRule,
  fetchAccounts,
  fetchCategories,
  fetchRules,
  testRule,
  updateAccount,
  updateCategory,
  updateRule,
  type Account,
  type AccountInput,
  type Category,
  type CategoryGroup,
  type CategoryKind,
  type MatchType,
  type Rule,
} from "../api";

const TABS = [
  { id: "accounts", label: "Accounts" },
  { id: "categories", label: "Categories" },
  { id: "rules", label: "Merchant rules" },
] as const;
type TabId = (typeof TABS)[number]["id"];

const KIND_LABEL: Record<CategoryKind, string> = {
  income: "Income",
  expense: "Expenses",
  savings: "Savings & debt",
  transfer: "Transfers (not counted as spending)",
};
const MATCH_LABEL: Record<MatchType, string> = {
  contains: "contains",
  starts_with: "starts with",
  regex: "regex",
};
const ACCOUNT_KIND_LABEL = { checking: "Checking", savings: "Savings", credit_card: "Credit card" };

type Notify = (message: string, tone?: "good" | "bad") => void;

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const tab: TabId = TABS.some((t) => t.id === params.get("tab")) ? (params.get("tab") as TabId) : "accounts";
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">Settings</h1>
      <p className="mt-2 text-lg text-muted">
        The accounts, categories and merchant rules every import uses.
      </p>

      <div role="tablist" aria-label="Settings sections" className="mt-6 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            className={`btn ${tab === t.id ? "bg-ink text-ground" : "btn-secondary"}`}
            onClick={() => {
              setStatus(null);
              setParams({ tab: t.id });
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <p
        aria-live="polite"
        className={
          status
            ? `mt-4 rounded-2xl px-4 py-3 ${status.tone === "good" ? "bg-good-bg text-good-ink" : "bg-danger-bg text-danger-ink"}`
            : "sr-only"
        }
      >
        {status?.message ?? ""}
      </p>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="mt-6">
        {tab === "accounts" && <AccountsTab notify={notify} />}
        {tab === "categories" && <CategoriesTab notify={notify} />}
        {tab === "rules" && <RulesTab notify={notify} />}
      </div>
    </section>
  );
}

// ---------------- shared bits ----------------
function Loading({ what, error }: { what: string; error: unknown }) {
  if (error)
    return (
      <p className="rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
        Could not load {what}: {(error as Error).message}. Check that the database is connected and reload the
        page.
      </p>
    );
  return <p className="text-muted">Loading {what}…</p>;
}

function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl bg-surface p-4 md:p-6">{children}</div>;
}

function useSave<A, R>(fn: (a: A) => Promise<R>, keys: string[][], notify: Notify) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => keys.forEach((k) => qc.invalidateQueries({ queryKey: k })),
    onError: (e: Error) => notify(e.message, "bad"),
  });
}

function Swatch({ color }: { color: string | null }) {
  return (
    <span
      aria-hidden
      className="inline-block h-3.5 w-3.5 shrink-0 rounded-full border border-line"
      style={{ background: color ?? "var(--color-muted)" }}
    />
  );
}

// ---------------- accounts ----------------
const EMPTY_ACCOUNT: AccountInput = {
  name: "",
  institution: "",
  kind: "checking",
  owner: "Hernan",
  country: "US",
  last4: null,
  is_active: true,
};

function AccountsTab({ notify }: { notify: Notify }) {
  const { data, error } = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const save = useSave(
    (a: { id: number | "new"; body: AccountInput }) =>
      a.id === "new" ? createAccount(a.body) : updateAccount(a.id, a.body),
    [["accounts"]],
    notify,
  );

  if (!data) return <Loading what="accounts" error={error} />;

  const submit = (id: number | "new", body: AccountInput) =>
    save.mutate(
      { id, body },
      {
        onSuccess: () => {
          setEditing(null);
          notify(id === "new" ? `Account added: ${body.name}.` : `Account saved: ${body.name}.`);
        },
      },
    );

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        {editing !== "new" && (
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            Add account
          </button>
        )}
      </div>
      {editing === "new" && (
        <Panel>
          <AccountForm
            initial={EMPTY_ACCOUNT}
            submitLabel="Add account"
            busy={save.isPending}
            onCancel={() => setEditing(null)}
            onSubmit={(body) => submit("new", body)}
          />
        </Panel>
      )}
      <ul className="space-y-3">
        {data.map((a) => (
          <li key={a.account_id}>
            <Panel>
              {editing === a.account_id ? (
                <AccountForm
                  initial={a}
                  submitLabel="Save account"
                  busy={save.isPending}
                  onCancel={() => setEditing(null)}
                  onSubmit={(body) => submit(a.account_id, body)}
                />
              ) : (
                <AccountRow account={a} onEdit={() => setEditing(a.account_id)} />
              )}
            </Panel>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AccountRow({ account: a, onEdit }: { account: Account; onEdit: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <div className="font-semibold">
          {a.name}
          {!a.is_active && <span className="pill pill-muted ml-2">Inactive</span>}
        </div>
        <div className="text-sm text-muted">
          {a.institution} · {ACCOUNT_KIND_LABEL[a.kind]} · {a.owner} · {a.country}
          {a.last4 ? <span className="num"> · •••• {a.last4}</span> : " · last 4 not set"}
        </div>
      </div>
      <button className="btn btn-secondary" onClick={onEdit} aria-label={`Edit ${a.name}`}>
        Edit
      </button>
    </div>
  );
}

function AccountForm(props: {
  initial: AccountInput;
  submitLabel: string;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: AccountInput) => void;
}) {
  const [v, setV] = useState<AccountInput>({ ...EMPTY_ACCOUNT, ...props.initial });
  const set = <K extends keyof AccountInput>(k: K, value: AccountInput[K]) =>
    setV((old) => ({ ...old, [k]: value }));
  const last4Bad = !!v.last4 && !/^\d{4}$/.test(v.last4);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (last4Bad) return;
    const { name, institution, kind, owner, country, last4, is_active } = v;
    props.onSubmit({
      name: name.trim(),
      institution: institution.trim(),
      kind,
      owner,
      country,
      last4: last4 || null,
      is_active,
    });
  };

  return (
    <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-3">
      <label>
        <span className="label">Name</span>
        <input
          className="field"
          required
          maxLength={100}
          value={v.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Institution</span>
        <input
          className="field"
          required
          maxLength={100}
          value={v.institution}
          onChange={(e) => set("institution", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Type</span>
        <select
          className="field"
          value={v.kind}
          onChange={(e) => set("kind", e.target.value as AccountInput["kind"])}
        >
          {Object.entries(ACCOUNT_KIND_LABEL).map(([k, l]) => (
            <option key={k} value={k}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Owner</span>
        <select
          className="field"
          value={v.owner}
          onChange={(e) => set("owner", e.target.value as AccountInput["owner"])}
        >
          <option>Hernan</option>
          <option>Lauren</option>
          <option>Joint</option>
        </select>
      </label>
      <label>
        <span className="label">Country</span>
        <select
          className="field"
          value={v.country}
          onChange={(e) => set("country", e.target.value as AccountInput["country"])}
        >
          <option value="US">United States</option>
          <option value="EC">Ecuador</option>
        </select>
      </label>
      <label>
        <span className="label">Last 4 digits (never the full number)</span>
        <input
          className="field num"
          inputMode="numeric"
          maxLength={4}
          value={v.last4 ?? ""}
          aria-invalid={last4Bad}
          aria-describedby={last4Bad ? "last4-error" : undefined}
          onChange={(e) => set("last4", e.target.value)}
        />
        {last4Bad && (
          <span id="last4-error" className="mt-1 block text-sm text-danger-ink">
            Enter exactly four digits.
          </span>
        )}
      </label>
      <label className="flex items-center gap-2 md:col-span-3">
        <input
          type="checkbox"
          className="h-5 w-5"
          checked={v.is_active}
          onChange={(e) => set("is_active", e.target.checked)}
        />
        Active (inactive accounts stay in history but are hidden from imports)
      </label>
      <div className="flex gap-2 md:col-span-3">
        <button type="submit" className="btn btn-primary" disabled={props.busy || last4Bad}>
          {props.submitLabel}
        </button>
        <button type="button" className="btn btn-quiet" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

// ---------------- categories ----------------
function CategoriesTab({ notify }: { notify: Notify }) {
  const { data, error } = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [adding, setAdding] = useState(false);
  const create = useSave(createCategory, [["categories"]], notify);

  if (!data) return <Loading what="categories" error={error} />;
  const kinds = Object.keys(KIND_LABEL) as CategoryKind[];

  return (
    <div className="space-y-8">
      <div className="flex justify-end">
        {!adding && (
          <button className="btn btn-primary" onClick={() => setAdding(true)}>
            Add group
          </button>
        )}
      </div>
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
        const groups = data.filter((g) => g.kind === kind);
        if (!groups.length) return null;
        return (
          <div key={kind}>
            <h2 className="font-display text-2xl font-bold">{KIND_LABEL[kind]}</h2>
            <ul className="mt-3 space-y-3">
              {groups.map((g) => (
                <li key={g.category_id}>
                  <GroupCard group={g} notify={notify} />
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function GroupForm(props: {
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

function GroupCard({ group: g, notify }: { group: CategoryGroup; notify: Notify }) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [newChild, setNewChild] = useState("");
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
          notify(`Category saved: ${body.name ?? c.name}.`);
        },
      },
    );

  return (
    <Panel>
      {editingId === g.category_id ? (
        <CategoryForm
          category={g}
          withColor
          busy={update.isPending}
          onCancel={() => setEditingId(null)}
          onSubmit={(body) => saveEdit(g, body)}
        />
      ) : (
        <CategoryLine category={g} heading onEdit={() => setEditingId(g.category_id)} />
      )}
      <ul className="mt-3 divide-y divide-line border-t border-line">
        {g.children.map((c) => (
          <li key={c.category_id} className="py-2 pl-6">
            {editingId === c.category_id ? (
              <CategoryForm
                category={c}
                busy={update.isPending}
                onCancel={() => setEditingId(null)}
                onSubmit={(body) => saveEdit(c, body)}
              />
            ) : (
              <CategoryLine category={c} onEdit={() => setEditingId(c.category_id)} />
            )}
          </li>
        ))}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-end gap-2 pl-6"
        onSubmit={(e) => {
          e.preventDefault();
          const name = newChild.trim();
          if (!name) return;
          create.mutate(
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
        <button type="submit" className="btn btn-secondary" disabled={create.isPending}>
          Add subcategory
        </button>
      </form>
    </Panel>
  );
}

function CategoryLine(props: { category: Category; heading?: boolean; onEdit: () => void }) {
  const c = props.category;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        {props.heading && <Swatch color={c.color} />}
        <span className={props.heading ? "text-lg font-semibold" : ""}>{c.name}</span>
        {c.is_fixed && <span className="pill bg-info-bg text-ink">Fixed</span>}
        {!c.is_active && <span className="pill pill-muted">Hidden</span>}
      </div>
      <button className="btn btn-quiet" onClick={props.onEdit} aria-label={`Edit ${c.name}`}>
        Edit
      </button>
    </div>
  );
}

function CategoryForm(props: {
  category: Category;
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
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        props.onSubmit({
          name: name.trim(),
          is_fixed: fixed,
          is_active: active,
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

// ---------------- merchant rules ----------------
function categoryOptions(groups: CategoryGroup[]) {
  return groups.flatMap((g) => [
    { id: g.category_id, label: g.name },
    ...g.children.map((c) => ({ id: c.category_id, label: `${g.name} / ${c.name}` })),
  ]);
}

function RulesTab({ notify }: { notify: Notify }) {
  const rules = useQuery({ queryKey: ["rules"], queryFn: fetchRules });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState("");
  const create = useSave(createRule, [["rules"]], notify);
  const update = useSave(
    (a: { id: number; body: Partial<Rule> }) => updateRule(a.id, a.body),
    [["rules"]],
    notify,
  );
  const remove = useSave(deleteRule, [["rules"]], notify);

  if (!rules.data || !cats.data) return <Loading what="merchant rules" error={rules.error ?? cats.error} />;
  const options = categoryOptions(cats.data);
  const q = filter.trim().toUpperCase();
  const shown = q
    ? rules.data.filter(
        (r) => r.pattern.toUpperCase().includes(q) || r.category_path.toUpperCase().includes(q),
      )
    : rules.data;

  return (
    <div className="space-y-6">
      <RuleTester />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="min-w-56 flex-1 md:max-w-sm">
          <span className="label">Filter rules</span>
          <input className="field" type="search" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </label>
        {!adding && (
          <button className="btn btn-primary" onClick={() => setAdding(true)}>
            Add rule
          </button>
        )}
      </div>

      {adding && (
        <Panel>
          <RuleForm
            options={options}
            busy={create.isPending}
            onCancel={() => setAdding(false)}
            onSubmit={(body) =>
              create.mutate(body, {
                onSuccess: (r) => {
                  setAdding(false);
                  notify(`Rule added: ${r.pattern} → ${r.category_path}.`);
                },
              })
            }
          />
        </Panel>
      )}

      <p className="text-sm text-muted">
        Rules run in priority order (lowest number first); the first active match wins. Matching ignores upper
        and lower case.
      </p>
      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full text-left">
          <thead className="bg-surface text-sm text-muted">
            <tr>
              <th className="px-4 py-3 font-semibold">Pattern</th>
              <th className="px-4 py-3 font-semibold">Match</th>
              <th className="px-4 py-3 font-semibold">Category</th>
              <th className="px-4 py-3 text-right font-semibold">Priority</th>
              <th className="px-4 py-3 font-semibold">Active</th>
              <th className="px-4 py-3">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {shown.map((r) => (
              <tr key={r.rule_id} className={r.is_active ? "" : "text-muted"}>
                <td className="px-4 py-2 font-mono text-sm">{r.pattern}</td>
                <td className="px-4 py-2 text-sm">{MATCH_LABEL[r.match_type]}</td>
                <td className="px-4 py-2">{r.category_path}</td>
                <td className="num px-4 py-2 text-right">{r.priority}</td>
                <td className="px-4 py-2">
                  <input
                    type="checkbox"
                    className="h-5 w-5"
                    aria-label={`Rule ${r.pattern} active`}
                    checked={r.is_active}
                    onChange={(e) =>
                      update.mutate(
                        { id: r.rule_id, body: { is_active: e.target.checked } },
                        {
                          onSuccess: (saved) =>
                            notify(`Rule ${saved.is_active ? "turned on" : "turned off"}: ${saved.pattern}.`),
                        },
                      )
                    }
                  />
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    className="btn btn-danger h-9 px-4 text-sm"
                    aria-label={`Delete rule ${r.pattern}`}
                    onClick={() => {
                      if (!window.confirm(`Delete the rule "${r.pattern}"?`)) return;
                      remove.mutate(r.rule_id, {
                        onSuccess: () => notify(`Rule deleted: ${r.pattern}.`),
                      });
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {!shown.length && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  No rules match “{filter}”.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RuleForm(props: {
  options: { id: number; label: string }[];
  busy: boolean;
  onCancel: () => void;
  onSubmit: (b: { pattern: string; match_type: MatchType; category_id: number; priority: number }) => void;
}) {
  const [pattern, setPattern] = useState("");
  const [matchType, setMatchType] = useState<MatchType>("contains");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [priority, setPriority] = useState(50);
  return (
    <form
      className="grid gap-4 md:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (categoryId === "") return;
        props.onSubmit({
          pattern: pattern.trim(),
          match_type: matchType,
          category_id: categoryId,
          priority,
        });
      }}
    >
      <label className="md:col-span-2">
        <span className="label">Pattern in the statement description</span>
        <input
          className="field font-mono"
          required
          maxLength={200}
          value={pattern}
          onChange={(e) => setPattern(e.target.value)}
        />
      </label>
      <label>
        <span className="label">Match</span>
        <select
          className="field"
          value={matchType}
          onChange={(e) => setMatchType(e.target.value as MatchType)}
        >
          {(Object.keys(MATCH_LABEL) as MatchType[]).map((m) => (
            <option key={m} value={m}>
              {MATCH_LABEL[m]}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Priority (lower runs first)</span>
        <input
          className="field num"
          type="number"
          min={0}
          max={1000}
          value={priority}
          onChange={(e) => setPriority(Number(e.target.value))}
        />
      </label>
      <label className="md:col-span-2">
        <span className="label">Category</span>
        <select
          className="field"
          required
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}
        >
          <option value="">Choose a category</option>
          {props.options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <div className="flex items-end gap-2 md:col-span-2">
        <button type="submit" className="btn btn-primary" disabled={props.busy}>
          Add rule
        </button>
        <button type="button" className="btn btn-quiet" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function RuleTester() {
  const [text, setText] = useState("");
  const tester = useMutation({ mutationFn: testRule });
  const result = tester.data;
  return (
    <Panel>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) tester.mutate(text.trim());
        }}
      >
        <label className="min-w-56 flex-1">
          <span className="label">Try a statement description</span>
          <input
            className="field font-mono"
            placeholder="UBER EATS SAN JOSE"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-secondary" disabled={tester.isPending}>
          Test rules
        </button>
      </form>
      <div aria-live="polite" className="mt-3 min-h-6">
        {tester.error && <span className="text-danger-ink">{tester.error.message}</span>}
        {result &&
          (result.rule ? (
            <span>
              Matches <code className="font-mono">{result.rule.pattern}</code> →{" "}
              <strong>{result.rule.category_path}</strong>
            </span>
          ) : (
            <span className="rounded-full bg-attention-bg px-3 py-1 text-attention-ink">
              No rule matches; this line would go to review.
            </span>
          ))}
      </div>
    </Panel>
  );
}
