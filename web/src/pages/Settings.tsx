import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import {
  createAccount,
  createCategory,
  deleteCategory,
  fetchCategoryUses,
  createRule,
  deleteRule,
  fetchAccounts,
  fetchCategories,
  fetchRules,
  fetchBankSync,
  runBankSync,
  linkBankSync,
  fetchRuleSuggestions,
  fetchSettings,
  putSetting,
  testRule,
  updateAccount,
  updateCategory,
  updateRule,
  type Account,
  type AccountInput,
  type Category,
  type CategoryGroup,
  type CategoryKind,
  type CategoryUses,
  type MatchType,
  type Rule,
  type RuleInput,
  type BankSync,
  type Owner,
  type RuleSuggestion,
} from "../api";
import CategoryPicker, { fold } from "../components/CategoryPicker";
import { money } from "../money";

const TABS = [
  { id: "accounts", label: "Accounts" },
  { id: "categories", label: "Categories" },
  { id: "rules", label: "Merchant rules" },
  { id: "sync", label: "Bank sync" },
] as const;
type TabId = (typeof TABS)[number]["id"];

const KIND_LABEL: Record<CategoryKind, string> = {
  income: "Income",
  expense: "Expenses",
  savings: "Savings and investing",
  debt: "Debt payments (loans, a house being paid off)",
  transfer: "Transfers (not counted as spending)",
};
const MATCH_LABEL: Record<MatchType, string> = {
  contains: "contains",
  starts_with: "starts with",
  regex: "regex",
};
/** "any amount", "up to 299.99", "from 300", "50 to 100" — on the amount without its sign. */
export function amountRange(r: Pick<Rule, "amount_min" | "amount_max">): string {
  const lo = r.amount_min ? money(r.amount_min) : null;
  const hi = r.amount_max ? money(r.amount_max) : null;
  if (lo && hi) return `${lo} to ${hi}`;
  if (lo) return `from ${lo}`;
  if (hi) return `up to ${hi}`;
  return "any amount";
}

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
        {tab === "sync" && <BankSyncTab notify={notify} />}
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

/** SimpleFIN accounts and the app account each one feeds (ADR-044). */
function BankSyncTab({ notify }: { notify: Notify }) {
  const qc = useQueryClient();
  const sync = useQuery({ queryKey: ["bank-sync"], queryFn: fetchBankSync });
  const done = (b: BankSync) => {
    qc.setQueryData(["bank-sync"], b);
    ["transactions", "review", "cashflow", "spending", "home"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k] }),
    );
  };
  const run = useMutation({
    mutationFn: () => runBankSync(false),
    onSuccess: (b) => {
      done(b);
      notify(`Synced: ${b.added ?? 0} new ${b.added === 1 ? "line" : "lines"}.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const link = useMutation({
    mutationFn: linkBankSync,
    onSuccess: (b) => {
      done(b);
      notify("Saved. The next sync brings that account's movements.");
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const b = sync.data;
  if (sync.error)
    return (
      <section role="alert" className="card space-y-3 p-5">
        <h2 className="text-lg font-semibold">Bank sync didn’t load</h2>
        <p className="text-sm text-muted">{(sync.error as Error).message}</p>
        <button className="btn btn-secondary" onClick={() => void sync.refetch()}>
          Try again
        </button>
      </section>
    );
  if (!b) return <p className="text-muted">Loading…</p>;
  if (!b.configured)
    return (
      <section className="card space-y-2 p-5">
        <h2 className="text-lg font-semibold">Bank sync is not set up</h2>
        <p className="text-sm text-muted">
          Connect your banks on SimpleFIN Bridge, make a setup token and run{" "}
          <code className="font-mono">./infra/azure/setup-simplefin.sh</code>.
        </p>
      </section>
    );
  const last = b.last_run;
  return (
    <div className="space-y-4">
      <section className="card flex flex-wrap items-center justify-between gap-3 p-5">
        <div>
          <h2 className="text-lg font-semibold">Bank sync</h2>
          <p className="text-sm text-muted">
            {last ? `Last synced ${new Date(last.at + "Z").toLocaleString()}` : "Not synced yet"} ·{" "}
            {b.pending_lines} synced {b.pending_lines === 1 ? "line waits" : "lines wait"} for a statement.
            It syncs by itself when you open the app, twice a day at most.
          </p>
        </div>
        <button className="btn btn-primary" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Syncing…" : "Sync now"}
        </button>
      </section>
      {last?.errors.map((e) => (
        <p key={e} role="alert" className="card border-warn p-4 text-sm text-warn">
          SimpleFIN: {e}
        </p>
      ))}
      {last && (
        <section aria-label="Accounts SimpleFIN reaches" className="card overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-line">
                <th className="px-4 py-2 text-sm font-semibold text-muted">Bank account</th>
                <th className="px-4 py-2 text-right text-sm font-semibold text-muted">Balance</th>
                <th className="px-4 py-2 text-sm font-semibold text-muted">Feeds this account</th>
              </tr>
            </thead>
            <tbody>
              {last.accounts.map((a) => {
                const mine = b.accounts.find((x) => x.sync_id === a.sync_id);
                return (
                  <tr key={a.sync_id} className="border-b border-line last:border-0">
                    <td className="px-4 py-2">
                      <span className="font-semibold">{a.org}</span> · {a.name}
                      <span className="block text-sm text-muted">{a.movements} movements in the last 44 days</span>
                    </td>
                    <td className="num px-4 py-2 text-right">{a.balance ? money(a.balance) : "—"}</td>
                    <td className="px-4 py-2">
                      <select
                        className="field"
                        aria-label={`App account for ${a.org} ${a.name}`}
                        value={mine?.account_id ?? ""}
                        disabled={link.isPending}
                        onChange={(e) =>
                          link.mutate({
                            sync_id: a.sync_id,
                            account_id: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                      >
                        <option value="">Not linked</option>
                        {b.accounts.map((x) => (
                          <option key={x.account_id} value={x.account_id}>
                            {x.institution} · {x.name}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
      <p className="text-sm text-muted">
        Synced lines are pending until the month’s statement is approved; then each statement line takes
        its place and keeps the category, person and notes you gave it.
      </p>
    </div>
  );
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
  closed_on: null,
};

const closedLabel = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

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
          {a.closed_on && <span className="pill pill-muted ml-2">Closed {closedLabel(a.closed_on)}</span>}
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
    const { name, institution, kind, owner, country, last4, is_active, closed_on } = v;
    props.onSubmit({
      name: name.trim(),
      institution: institution.trim(),
      kind,
      owner,
      country,
      last4: last4 || null,
      is_active,
      closed_on: closed_on || null,
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
      <div className="md:col-span-3 md:max-w-xs">
        <label>
          <span className="label">Closed or suspended on (optional)</span>
          <input
            className="field"
            type="date"
            value={v.closed_on ?? ""}
            onChange={(e) => set("closed_on", e.target.value || null)}
            aria-describedby="closed-help"
          />
        </label>
        <span id="closed-help" className="mt-1 block text-sm text-muted">
          Data Status stops expecting statements after this day; earlier ones still load.
        </span>
      </div>
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

function GroupCard({
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
function DeleteCategory({
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

function SubcategoryAdd({
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

function CategoryLine(props: { category: Category; heading?: boolean; total?: number; onEdit: () => void }) {
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

function CategoryForm(props: {
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

// ---------------- merchant rules ----------------
export function appliedNote(r: Pick<Rule, "applied">): string {
  const n = r.applied ?? 0;
  return n ? ` It categorized ${n} ${n === 1 ? "line" : "lines"} that needed a category.` : "";
}

function RulesTab({ notify }: { notify: Notify }) {
  const rules = useQuery({ queryKey: ["rules"], queryFn: fetchRules });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState("");
  // A saved rule also categorizes loaded and waiting lines, so those views refresh too.
  const reach = [["rules"], ["review"], ["transactions"], ["batch"]];
  const create = useSave(createRule, reach, notify);
  const update = useSave((a: { id: number; body: Partial<Rule> }) => updateRule(a.id, a.body), reach, notify);
  const remove = useSave(deleteRule, [["rules"]], notify);

  if (!rules.data || !cats.data) return <Loading what="merchant rules" error={rules.error ?? cats.error} />;
  const q = filter.trim().toUpperCase();
  const shown = q
    ? rules.data.filter(
        (r) => r.pattern.toUpperCase().includes(q) || r.category_path.toUpperCase().includes(q),
      )
    : rules.data;

  return (
    <div className="space-y-6">
      <RuleTester />
      <SuggestedRules notify={notify} reach={reach} />

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
            busy={create.isPending}
            onCancel={() => setAdding(false)}
            onSubmit={(body) =>
              create.mutate(body, {
                onSuccess: (r) => {
                  setAdding(false);
                  notify(`Rule added: ${r.pattern} → ${r.category_path}.${appliedNote(r)}`);
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
              <th className="px-4 py-3 font-semibold">Amount</th>
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
                <td className="px-4 py-2">
                  {r.category_path}
                  {(r.set_person || r.merchant_name) && (
                    <span className="block text-sm text-muted">{alsoNote(r)}</span>
                  )}
                </td>
                <td className={`num px-4 py-2 text-sm ${r.amount_min || r.amount_max ? "" : "text-muted"}`}>
                  {amountRange(r)}
                </td>
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
                            notify(
                              `Rule ${saved.is_active ? "turned on" : "turned off"}: ${saved.pattern}.${appliedNote(saved)}`,
                            ),
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
                <td colSpan={7} className="px-4 py-6 text-center text-muted">
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

export function alsoNote(r: Pick<Rule, "set_person" | "merchant_name">): string {
  const parts = [
    r.set_person && `person ${r.set_person}`,
    r.merchant_name && `name “${r.merchant_name}”`,
  ].filter(Boolean);
  return parts.length ? `Also sets ${parts.join(" and ")}` : "";
}

const DISMISSED = "rule_suggestions_dismissed";

/** Merchants categorized the same way at least twice by hand, offered as rules (ADR-042). */
function SuggestedRules({ notify, reach }: { notify: Notify; reach: string[][] }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["rules", "suggestions"], queryFn: fetchRuleSuggestions });
  const me = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const save = useSave(createRule, reach, notify);
  const raw = me.data?.settings[DISMISSED];
  const dismissed = Array.isArray(raw) ? (raw as string[]) : [];
  const shown = (list.data ?? []).filter((s) => !dismissed.includes(s.pattern));
  if (!shown.length) return null;
  const dismiss = (s: RuleSuggestion) =>
    putSetting(DISMISSED, [...dismissed, s.pattern].slice(-200)).then(() =>
      qc.invalidateQueries({ queryKey: ["settings"] }),
    );
  return (
    <section aria-label="Suggested rules" className="card space-y-3 p-5">
      <div>
        <h2 className="text-lg font-semibold">Suggested rules</h2>
        <p className="text-sm text-muted">
          You categorized these the same way more than once. Save one and the next statements get it by
          themselves.
        </p>
      </div>
      <ul className="divide-y divide-line">
        {shown.map((s) => (
          <li key={s.pattern} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="font-mono text-sm">{s.pattern}</p>
              <p className="text-sm text-muted">
                → {s.category_path}
                {s.person ? ` · ${s.person}` : ""} · {s.times} times · e.g. {s.example}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className="btn btn-primary h-9 px-4 text-sm"
                disabled={save.isPending}
                aria-label={`Save rule ${s.pattern}`}
                onClick={() =>
                  save.mutate(
                    {
                      pattern: s.pattern,
                      match_type: "contains",
                      category_id: s.category_id,
                      priority: 50,
                      set_person: s.person,
                    },
                    {
                      onSuccess: (r) =>
                        notify(`Rule added: ${r.pattern} → ${r.category_path}.${appliedNote(r)}`),
                    },
                  )
                }
              >
                Save rule
              </button>
              <button
                className="btn btn-quiet h-9 px-4 text-sm"
                aria-label={`Not now ${s.pattern}`}
                onClick={() => void dismiss(s)}
              >
                Not now
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RuleForm(props: { busy: boolean; onCancel: () => void; onSubmit: (b: RuleInput) => void }) {
  const [pattern, setPattern] = useState("");
  const [person, setPerson] = useState<Owner | "">("");
  const [merchantName, setMerchantName] = useState("");
  const [matchType, setMatchType] = useState<MatchType>("contains");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [priority, setPriority] = useState(50);
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
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
          amount_min: amountMin.trim() || null,
          amount_max: amountMax.trim() || null,
          set_person: person || null,
          merchant_name: merchantName.trim() || null,
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
      <div className="md:col-span-2">
        <CategoryPicker
          label="Category"
          value={categoryId}
          onChange={setCategoryId}
          groups={groups}
          required
        />
      </div>
      <label>
        <span className="label">Only amounts from (optional)</span>
        <input
          className="field num"
          type="number"
          min={0}
          step="0.01"
          inputMode="decimal"
          value={amountMin}
          onChange={(e) => setAmountMin(e.target.value)}
        />
      </label>
      <label>
        <span className="label">Up to (optional)</span>
        <input
          className="field num"
          type="number"
          min={0}
          step="0.01"
          inputMode="decimal"
          value={amountMax}
          onChange={(e) => setAmountMax(e.target.value)}
        />
      </label>
      <p className="text-sm text-muted md:col-span-4">
        Amounts are compared without their sign: “up to 299.99” catches a 104.11 payment, not a 505.19 one.
      </p>
      <label>
        <span className="label">Also set person (optional)</span>
        <select className="field" value={person} onChange={(e) => setPerson(e.target.value as Owner | "")}>
          <option value="">Keep the account’s</option>
          <option value="Hernan">Hernan</option>
          <option value="Lauren">Lauren</option>
          <option value="Joint">Joint</option>
        </select>
      </label>
      <label>
        <span className="label">Show merchant as (optional)</span>
        <input
          className="field"
          maxLength={100}
          value={merchantName}
          onChange={(e) => setMerchantName(e.target.value)}
        />
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
  const [amount, setAmount] = useState("");
  const tester = useMutation({ mutationFn: testRule });
  const result = tester.data;
  return (
    <Panel>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) tester.mutate({ description: text.trim(), amount: amount.trim() || undefined });
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
        <label className="w-36">
          <span className="label">Amount (optional)</span>
          <input
            className="field num"
            type="number"
            step="0.01"
            inputMode="decimal"
            placeholder="-104.11"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
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
