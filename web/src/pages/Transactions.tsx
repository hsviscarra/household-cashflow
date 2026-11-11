import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import {
  fetchCategories,
  fetchHistory,
  fetchLineContext,
  fetchLineSource,
  fetchPeople,
  linkInvoice,
  statementPageUrl,
  fetchTransactions,
  removeSplit,
  splitTransaction,
  unlinkTransfer,
  updateTransaction,
  type Txn,
} from "../api";
import CategoryPicker from "../components/CategoryPicker";
import { LineDetails } from "../components/MerchantReview";
import { PersonNote, SaveView, TableSettings } from "../components/Personalize";
import { addMonths, money, monthLong, num, showAmount } from "../money";
import { personParam, useColumns, usePerson, useSavedViews, type Person } from "../prefs";

const SOURCE_LABEL: Record<string, string> = {
  statement: "Statement",
  excel_history: "Excel history",
  manual: "Manual",
};
const HOW: Record<string, string> = {
  rule: "by rule",
  section: "from the statement",
  manual: "chosen",
  suggestion: "Claude, accepted",
  excel: "workbook",
  split: "split part",
  match: "matched transfer",
  invoice: "from its invoice's products",
};

function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

// Columns a person can choose (ADR-026, ADR-030); the description and the amount always show.
const COLUMNS: Record<string, string> = {
  date: "Date",
  account: "Account",
  who: "Who",
  category: "Category",
  note: "Note / person",
  merchant: "Merchant (cleaned)",
  post: "Posted date",
  country: "Country",
};
const DEFAULT_COLUMNS = ["date", "account", "who", "category", "note"];

export type Filters = {
  q: string;
  todo: boolean;
  account: string | null;
  group: string | null;
  min: number | null;
  max: number | null;
  note: boolean;
};

const group = (t: Txn) => t.category_path?.split(/\s[/›]\s/)[0] ?? null;

/** The filters: search (description, merchant, note, category, account or amount), needs a
 * category, account, category group, amount range (without sign) and has a note. */
export function keep(t: Txn, f: Filters) {
  if (f.todo && (t.parts || t.category_id)) return false;
  if (f.account && t.account_name !== f.account) return false;
  if (f.group && group(t) !== f.group) return false;
  const size = Math.abs(num(t.amount));
  if (f.min !== null && size < f.min) return false;
  if (f.max !== null && size > f.max) return false;
  if (f.note && !t.notes) return false;
  const words = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  const text = [t.description, t.merchant, t.notes, t.category_path, t.account_name, size.toFixed(2)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return words.every((w) => text.includes(w.replace(/[$,]/g, "")));
}

/** Kept for the tests and saved views of 0.42: search and "needs a category". */
export const matches = (t: Txn, q: string, todo: boolean) =>
  keep(t, { q, todo, account: null, group: null, min: null, max: null, note: false });

/** Lines that count: a split line counts through its parts. */
export const counted = (t: Txn) => !t.parts;

const cell = (v: string | null | undefined) => {
  const text = v ?? "";
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

/** The lines shown, as CSV (the columns of the table, every one). */
export function toCsv(rows: Txn[], names: Map<number, string>) {
  const head = [
    "Date",
    "Posted",
    "Description",
    "Merchant",
    "Account",
    "Who",
    "Category",
    "Note",
    "Person",
    "Country",
    "Amount",
  ];
  const body = rows.map((t) =>
    [
      t.txn_date,
      t.post_date,
      t.description,
      t.merchant,
      t.account_name,
      t.person,
      t.category_path,
      t.notes,
      t.counterparty_id ? names.get(t.counterparty_id) : null,
      t.country,
      t.amount,
    ]
      .map(cell)
      .join(","),
  );
  return [head.join(","), ...body].join("\n");
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const PERIODS: Record<string, string> = { "1": "This month", "3": "3 months to it", "12": "12 months to it" };

export default function TransactionsPage() {
  const [params, setParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : thisMonth();
  const months = ["3", "12"].includes(params.get("months") ?? "") ? Number(params.get("months")) : 1;
  const cp = Number(params.get("cp")) || null;
  const numOr = (k: string) =>
    params.get(k) && !Number.isNaN(Number(params.get(k))) ? Number(params.get(k)) : null;
  const f: Filters = {
    q: params.get("q") ?? "",
    todo: params.get("todo") === "1",
    account: params.get("acct"),
    group: params.get("cat"),
    min: numOr("min"),
    max: numOr("max"),
    note: params.get("note") === "1",
  };
  const [person, , ready] = usePerson();
  const [cols] = useColumns("transactions", Object.keys(COLUMNS), DEFAULT_COLUMNS);
  const show = (c: string) => cols.includes(c);
  const { data: loaded, error } = useQuery({
    queryKey: ["transactions", month, person, months, cp],
    queryFn: () =>
      fetchTransactions(`${month}-01`, personParam(person), { months, counterparty_id: cp ?? undefined }),
    enabled: ready,
  });
  const people = useQuery({ queryKey: ["people"], queryFn: fetchPeople });
  const names = new Map((people.data ?? []).map((p) => [p.counterparty_id, p.name]));
  const filtering =
    !!f.q.trim() || f.todo || !!f.account || !!f.group || f.min !== null || f.max !== null || f.note;
  const data = loaded?.filter((t) => keep(t, f));
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: key === "q" || key === "min" || key === "max" });
  };
  useQuery({ queryKey: ["categories"], queryFn: fetchCategories }); // ready for the editors
  const [open, setOpen] = useState<number | null>(null);

  const out = (data ?? []).filter((t) => counted(t) && num(t.amount) < 0 && t.type !== "transfer");
  const totalOut = out.reduce((s, t) => s - num(t.amount), 0);
  const totalShown = (data ?? []).filter(counted).reduce((s, t) => s + num(t.amount), 0);
  const needing = (loaded ?? []).filter(
    (t) => counted(t) && !t.category_id && t.source === "statement",
  ).length;
  // Parts are listed right under the line they split.
  const rows = data ? ordered(data) : [];
  const accounts = [
    ...new Set((loaded ?? []).map((t) => t.account_name).filter((a): a is string => !!a)),
  ].sort();
  const groups = [...new Set((loaded ?? []).map(group).filter((g): g is string => !!g))].sort();
  const period =
    months > 1
      ? `${monthLong(addMonths(`${month}-01`, 1 - months))} to ${monthLong(`${month}-01`)}`
      : monthLong(`${month}-01`);

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-4xl font-bold leading-tight">Transactions</h1>
        {data && data.length > 0 && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() =>
              download(`transactions-${month}${months > 1 ? `-${months}m` : ""}.csv`, toCsv(rows, names))
            }
          >
            Export {data.length} lines (CSV)
          </button>
        )}
      </div>
      <p className="mt-2 text-lg text-muted">
        Every loaded line. Filter, choose your columns and save the view; click a line to edit it, split it or
        add a note. Every change is kept in its history.
      </p>

      <ViewTabs month={month} />

      <div className="mt-4 flex flex-wrap items-end gap-3" role="group" aria-label="Filters">
        <label>
          <span className="label">Month</span>
          <input
            type="month"
            className="field w-44"
            value={month}
            onChange={(e) => e.target.value && setParam("month", e.target.value)}
          />
        </label>
        <label>
          <span className="label">Period</span>
          <select
            className="field w-44"
            value={String(months)}
            onChange={(e) => setParam("months", e.target.value === "1" ? null : e.target.value)}
          >
            {Object.entries(PERIODS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Account</span>
          <select
            className="field w-48"
            value={f.account ?? ""}
            onChange={(e) => setParam("acct", e.target.value || null)}
          >
            <option value="">Any</option>
            {accounts.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Category</span>
          <select
            className="field w-48"
            value={f.group ?? ""}
            onChange={(e) => setParam("cat", e.target.value || null)}
          >
            <option value="">Any</option>
            {groups.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <fieldset className="flex items-end gap-1">
          <legend className="label">Amount</legend>
          <label>
            <span className="sr-only">From</span>
            <input
              className="field num w-24"
              inputMode="decimal"
              placeholder="from"
              value={params.get("min") ?? ""}
              onChange={(e) => setParam("min", e.target.value.trim() || null)}
            />
          </label>
          <span className="pb-3 text-muted">–</span>
          <label>
            <span className="sr-only">Up to</span>
            <input
              className="field num w-24"
              inputMode="decimal"
              placeholder="up to"
              value={params.get("max") ?? ""}
              onChange={(e) => setParam("max", e.target.value.trim() || null)}
            />
          </label>
        </fieldset>
        <label>
          <span className="label">Search</span>
          <input
            type="search"
            className="field w-64"
            value={f.q}
            placeholder="Description, merchant, note, amount"
            onChange={(e) => setParam("q", e.target.value)}
          />
        </label>
        <label className="flex h-11 items-center gap-2">
          <input
            type="checkbox"
            checked={f.todo}
            onChange={(e) => setParam("todo", e.target.checked ? "1" : null)}
          />
          Needs a category
        </label>
        <label className="flex h-11 items-center gap-2">
          <input
            type="checkbox"
            checked={f.note}
            onChange={(e) => setParam("note", e.target.checked ? "1" : null)}
          />
          Has a note
        </label>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SaveView month={monthLong(`${month}-01`)} />
          <TableSettings table="transactions" columns={COLUMNS} defaults={DEFAULT_COLUMNS} />
        </div>
      </div>
      {cp && (
        <p className="mt-4 inline-flex flex-wrap items-center gap-2 rounded-full bg-info-bg px-4 py-1.5 text-sm">
          Only {names.get(cp) ?? "this person"}’s lines.
          <button type="button" className="font-semibold underline" onClick={() => setParam("cp", null)}>
            Everyone
          </button>
        </p>
      )}
      <PersonNote person={person} />

      {error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the transactions: {(error as Error).message}
        </p>
      )}
      {needing > 0 && (
        <p className="mt-6 rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink">
          {needing} {needing === 1 ? "line needs" : "lines need"} a category.{" "}
          <Link to={`/review?month=${month}`} className="font-semibold underline">
            Review them
          </Link>
        </p>
      )}
      {data?.some((t) => t.source === "excel_history") && data.some((t) => t.source === "statement") && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">
          {period} is covered by the Excel history, so the totals on Cash flow use the workbook. The statement
          lines below are kept for reference and don’t count twice.
        </p>
      )}
      {data && !data.length && filtering && !!loaded?.length && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">No lines match these filters.</p>
      )}
      {loaded && !loaded.length && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">
          Nothing loaded for {period} yet. Upload and approve a statement on the Import page.
        </p>
      )}

      {data && data.length > 0 && (
        <ul
          className="mt-6 divide-y divide-line rounded-2xl border border-line md:hidden"
          aria-label="Transactions (list)"
        >
          {rows.map((t) => (
            <li key={t.transaction_id} className={`px-4 py-3 ${t.parent_transaction_id ? "pl-8" : ""}`}>
              <div className="flex items-baseline justify-between gap-3">
                <span className={`font-semibold ${t.parts ? "text-muted line-through" : ""}`}>
                  {t.parent_transaction_id && <span aria-hidden>↳ </span>}
                  {t.description}
                </span>
                <span className={`num shrink-0 ${t.parts ? "text-muted line-through" : ""}`}>
                  {showAmount(t.amount)}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
                <span className="num">{day(t.txn_date)}</span>
                <span>· {t.account_name ?? SOURCE_LABEL[t.source] ?? t.source}</span>
                {t.person && <span>· {t.person}</span>}
                <span>·</span>
                <CategoryCell t={t} />
              </div>
              <NoteCell t={t} names={names} />
              <EditToggle t={t} open={open} setOpen={setOpen} />
              {open === t.transaction_id && (
                <div className="mt-3">
                  <TxnEditor t={t} onDone={() => setOpen(null)} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {data && data.length > 0 && (
        <div className="mt-6 hidden overflow-x-auto rounded-2xl border border-line md:block">
          <table className="w-full text-sm">
            <caption className="sr-only">Transactions in {period}</caption>
            <thead className="bg-surface text-muted">
              <tr>
                {show("date") && <Th>Date</Th>}
                {show("post") && <Th>Posted</Th>}
                <Th>Description</Th>
                {show("merchant") && <Th>Merchant</Th>}
                {show("category") && <Th>Category</Th>}
                {show("account") && <Th>Account</Th>}
                {show("who") && <Th>Who</Th>}
                {show("note") && <Th>Note / person</Th>}
                {show("country") && <Th>Country</Th>}
                <th scope="col" className="px-4 py-2 text-right font-semibold">
                  Amount
                </th>
                <th scope="col" className="px-4 py-2">
                  <span className="sr-only">Edit</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((t) => (
                <Fragment key={t.transaction_id}>
                  <tr className={t.parts ? "text-muted" : ""}>
                    {show("date") && <td className="num whitespace-nowrap px-4 py-2">{day(t.txn_date)}</td>}
                    {show("post") && (
                      <td className="num whitespace-nowrap px-4 py-2">
                        {t.post_date ? day(t.post_date) : ""}
                      </td>
                    )}
                    <td className={`px-4 py-2 ${t.parent_transaction_id ? "pl-8" : ""}`}>
                      {t.parent_transaction_id && <span aria-hidden>↳ </span>}
                      <span className={t.parts ? "line-through" : ""}>{t.description}</span>
                      {!show("note") && t.notes && (
                        <span className="block text-xs text-muted">{t.notes}</span>
                      )}
                    </td>
                    {show("merchant") && <td className="px-4 py-2 text-muted">{t.merchant}</td>}
                    {show("category") && (
                      <td className="px-4 py-2">
                        <CategoryCell t={t} />
                      </td>
                    )}
                    {show("account") && (
                      <td className="px-4 py-2 text-muted">
                        {t.account_name ?? SOURCE_LABEL[t.source] ?? t.source}
                      </td>
                    )}
                    {show("who") && <td className="px-4 py-2">{t.person}</td>}
                    {show("note") && (
                      <td className="px-4 py-2">
                        <NoteCell t={t} names={names} />
                      </td>
                    )}
                    {show("country") && <td className="px-4 py-2 text-muted">{t.country}</td>}
                    <td className={`num px-4 py-2 text-right ${t.parts ? "line-through" : ""}`}>
                      {showAmount(t.amount)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <EditToggle t={t} open={open} setOpen={setOpen} />
                    </td>
                  </tr>
                  {open === t.transaction_id && (
                    <tr>
                      <td colSpan={3 + cols.length} className="bg-surface px-4 py-4">
                        <TxnEditor t={t} onDone={() => setOpen(null)} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.length > 0 && (
        <p className="mt-3 flex flex-wrap justify-between gap-2 text-sm text-muted">
          <span>
            {period}: {data.length} {filtering ? `of ${loaded!.length} ` : ""}lines ·{" "}
            <span className="num">{money(totalOut)}</span> out (card payments and transfers excluded)
          </span>
          <span>
            Total shown <span className="num text-ink">{showAmount(totalShown)}</span>
          </span>
        </p>
      )}
    </section>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th scope="col" className="px-4 py-2 text-left font-semibold">
      {children}
    </th>
  );
}

function NoteCell({ t, names }: { t: Txn; names: Map<number, string> }) {
  const who = t.counterparty_id ? names.get(t.counterparty_id) : null;
  if (!who && !t.notes) return null;
  return (
    <span className="block text-sm">
      {who && (
        <Link to={`/transactions?cp=${t.counterparty_id}&months=12`} className="pill pill-muted mr-1">
          {who}
        </Link>
      )}
      {t.notes && <span className="text-muted">{t.notes}</span>}
    </span>
  );
}

/** Saved views of this page as tabs (ADR-030): "All" and each view saved here. */
function ViewTabs({ month }: { month: string }) {
  const { views } = useSavedViews();
  const [, setPerson] = usePerson();
  const { search } = useLocation();
  const mine = views.filter((v) => v.path === "/transactions");
  const strip = (q: string) => {
    const p = new URLSearchParams(q);
    p.delete("month");
    p.sort();
    return p.toString();
  };
  const here = strip(search);
  return (
    <nav aria-label="Saved views" className="mt-6 flex flex-wrap gap-1 border-b border-line">
      {[{ id: "all", name: "All", search: "", person: null as Person | null }, ...mine].map((v) => {
        const on = strip(v.search) === here;
        const q = new URLSearchParams(v.search);
        if (!q.has("month")) q.set("month", month);
        return (
          <Link
            key={v.id}
            to={`/transactions?${q.toString()}`}
            aria-current={on ? "page" : undefined}
            onClick={() => v.person && setPerson(v.person)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold ${on ? "border-primary text-ink" : "border-transparent text-muted hover:text-ink"}`}
          >
            {v.name}
          </Link>
        );
      })}
    </nav>
  );
}

function ordered(txns: Txn[]): Txn[] {
  const parts = new Map<number, Txn[]>();
  for (const t of txns)
    if (t.parent_transaction_id)
      parts.set(t.parent_transaction_id, [...(parts.get(t.parent_transaction_id) ?? []), t]);
  return txns
    .filter((t) => !t.parent_transaction_id)
    .flatMap((t) => [
      t,
      ...(parts.get(t.transaction_id) ?? []).sort((a, b) => a.transaction_id - b.transaction_id),
    ]);
}

function CategoryCell({ t }: { t: Txn }) {
  if (t.parts) return <span className="pill pill-muted">Split into {t.parts}</span>;
  if (!t.category_path)
    return <span className="pill bg-attention-bg text-attention-ink">Needs a category</span>;
  return (
    <span>
      {t.category_path}
      {t.category_source && t.category_source !== "split" && t.category_source !== "match" && (
        <span className="text-xs text-muted"> · {HOW[t.category_source] ?? t.category_source}</span>
      )}
      {t.transfer_with && (
        <span className="block text-xs text-muted">
          ↔ {t.transfer_with.account_name ?? "another account"}, {day(t.transfer_with.txn_date)}
        </span>
      )}
    </span>
  );
}

function UnlinkTransfer({ t }: { t: Txn }) {
  const invalidate = useInvalidate();
  const unlink = useMutation({
    mutationFn: () => unlinkTransfer(t.transfer_group_id!),
    onSuccess: invalidate,
  });
  if (!t.transfer_group_id || !t.transfer_with) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-info-bg px-4 py-3 text-sm">
      <span>
        Matched transfer: the other side is <strong>{t.transfer_with.description}</strong> on{" "}
        {t.transfer_with.account_name ?? "another account"}, {day(t.transfer_with.txn_date)} (
        <span className="num">{showAmount(t.transfer_with.amount)}</span>).
      </span>
      <button
        type="button"
        className="btn btn-quiet h-9 px-3"
        disabled={unlink.isPending}
        onClick={() => unlink.mutate()}
      >
        Not the same money: unlink
      </button>
      {unlink.error && <span className="text-danger-ink">{(unlink.error as Error).message}</span>}
    </div>
  );
}

function EditToggle({
  t,
  open,
  setOpen,
}: {
  t: Txn;
  open: number | null;
  setOpen: (id: number | null) => void;
}) {
  const isOpen = open === t.transaction_id;
  return (
    <button
      className="btn btn-quiet h-9 px-3 text-sm"
      aria-expanded={isOpen}
      aria-label={`${isOpen ? "Close" : "Edit"} ${t.description} on ${day(t.txn_date)}`}
      onClick={() => setOpen(isOpen ? null : t.transaction_id)}
    >
      {isOpen ? "Close" : "Edit"}
    </button>
  );
}

function useInvalidate() {
  const qc = useQueryClient();
  return () =>
    ["transactions", "review", "cashflow", "transfers"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k] }),
    );
}

function TxnEditor({ t, onDone }: { t: Txn; onDone: () => void }) {
  const invalidate = useInvalidate();
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
  const [categoryId, setCategoryId] = useState<number | "">(t.category_id ?? "");
  const [notes, setNotes] = useState(t.notes ?? "");
  const [message, setMessage] = useState<{ text: string; undo?: () => void; bad?: boolean } | null>(null);
  const history = useQuery({
    queryKey: ["history", t.transaction_id],
    queryFn: () => fetchHistory(t.transaction_id),
  });
  const save = useMutation({
    mutationFn: (body: { category_id?: number; notes?: string | null }) =>
      updateTransaction(t.transaction_id, body),
    onSuccess: () => {
      invalidate();
      history.refetch();
    },
    onError: (e: Error) => setMessage({ text: e.message, bad: true }),
  });
  const previous = t.category_id;

  return (
    <div className="space-y-4">
      {!t.parts && (
        <form
          className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            const body: { category_id?: number; notes?: string | null } = {};
            if (categoryId !== "" && categoryId !== t.category_id) body.category_id = categoryId;
            if ((notes.trim() || null) !== t.notes) body.notes = notes.trim() || null;
            if (!Object.keys(body).length) return onDone();
            save.mutate(body, {
              onSuccess: (saved) =>
                setMessage({
                  text: `Saved: ${saved.category_path ?? "no category"}.`,
                  undo:
                    body.category_id && previous
                      ? () =>
                          save.mutate(
                            { category_id: previous },
                            { onSuccess: () => setMessage({ text: "Change undone." }) },
                          )
                      : undefined,
                }),
            });
          }}
        >
          <CategoryPicker label="Category" value={categoryId} onChange={setCategoryId} groups={groups} />
          <label>
            <span className="label">Note</span>
            <input
              className="field"
              maxLength={1000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-secondary" disabled={save.isPending}>
            Save
          </button>
        </form>
      )}
      <div aria-live="polite" className="min-h-6 text-sm">
        {message && (
          <span className={message.bad ? "text-danger-ink" : "text-good-ink"}>
            {message.text}{" "}
            {message.undo && (
              <button type="button" className="font-semibold underline" onClick={message.undo}>
                Undo
              </button>
            )}
          </span>
        )}
      </div>

      <LineKnown
        t={t}
        onCategory={(id) => {
          setCategoryId(id);
          save.mutate(
            { category_id: id },
            { onSuccess: (saved) => setMessage({ text: `Saved: ${saved.category_path ?? "no category"}.` }) },
          );
        }}
      />

      <UnlinkTransfer t={t} />
      {!t.parent_transaction_id && !t.transfer_group_id && <SplitEditor t={t} />}

      <details>
        <summary className="cursor-pointer text-sm text-primary">History of this line</summary>
        {history.data && !history.data.length && (
          <p className="mt-2 text-sm text-muted">No changes since it was loaded.</p>
        )}
        {history.data && history.data.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm">
            {history.data.map((c) => (
              <li key={c.change_id}>
                <span className="num text-muted">{c.changed_at.slice(0, 16).replace("T", " ")}</span>{" "}
                {c.changed_by}: {c.column_name} {c.old_value ?? "—"} → {c.new_value ?? "—"}{" "}
                <span className="text-muted">({c.reason})</span>
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}

const shortDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

/** What's known about the line, to decide what it was (ADR-074): the statement, lines of the same
 * amount and their categories, the transfer's other side, the invoice, the rule, the card's
 * purpose. */
export function LineKnown({ t, onCategory }: { t: Txn; onCategory: (id: number) => void }) {
  const invalidate = useInvalidate();
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
  const ctx = useQuery({
    queryKey: ["line-context", t.transaction_id],
    queryFn: () => fetchLineContext(t.transaction_id),
  });
  const [showStatement, setShowStatement] = useState(false);
  const link = useMutation({
    mutationFn: (invoiceId: number) => linkInvoice(t.transaction_id, invoiceId),
    onSuccess: () => {
      ctx.refetch();
      invalidate();
    },
  });
  const byPath = new Map<string, number>(
    groups.flatMap((g) => g.children.map((c) => [`${g.name} / ${c.name}`, c.category_id] as const)),
  );
  const c = ctx.data;
  return (
    <section
      aria-label="What we know about this line"
      className="space-y-3 rounded-xl bg-surface p-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-3">
        <strong>What we know</strong>
        {t.statement_file_id && (
          <a
            className="text-primary underline"
            target="_blank"
            rel="noreferrer"
            href={statementPageUrl(t.statement_file_id, null)}
          >
            Open the statement
          </a>
        )}
        {t.statement_file_id && (
          <button
            type="button"
            className="text-primary underline"
            onClick={() => setShowStatement(!showStatement)}
          >
            {showStatement ? "Hide the statement text" : "Show where it is on the statement"}
          </button>
        )}
      </div>
      {showStatement && (
        <LineDetails id={t.transaction_id} source={{ scope: "loaded", fetch: fetchLineSource }} />
      )}
      {!c && !ctx.error && <p className="text-muted">Looking…</p>}
      {c?.purpose?.unusual && (
        <p className="rounded-lg bg-attention-bg px-2 py-1.5 text-attention-ink">
          This is {c.purpose.account_name}, kept for {c.purpose.for_whom}’s school (
          {c.purpose.usual.join(", ")}), and this doesn’t look like it. Check it.
        </p>
      )}
      {c && c.same_amount.length > 0 && (
        <div>
          <p className="text-muted">Other lines of exactly {money(t.amount)}:</p>
          <ul className="mt-1 space-y-1" aria-label="Lines of the same amount">
            {c.same_amount.map((x) => {
              const cid = x.category_path ? byPath.get(x.category_path) : undefined;
              return (
                <li key={x.transaction_id} className="flex flex-wrap items-center gap-2">
                  <span className="num">{shortDay(x.txn_date)}</span>
                  <span className="text-muted">{x.account_name}</span>
                  <span>→ {x.category_path ?? "no category"}</span>
                  {cid && cid !== t.category_id && (
                    <button
                      type="button"
                      className="btn btn-secondary h-7 px-2 text-xs"
                      onClick={() => onCategory(cid)}
                    >
                      Use this category
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {c && c.transfer_side.length > 0 && (
        <p>
          <span className="text-muted">Other side: </span>
          {c.transfer_side
            .map((x) => `${x.account_name} ${shortDay(x.txn_date)} ${money(x.amount)}`)
            .join("; ")}
        </p>
      )}
      {c && c.transfer_candidates.length > 0 && (
        <div>
          <p className="text-muted">Could be the other side (same amount, within a week):</p>
          <ul className="mt-1 space-y-0.5">
            {c.transfer_candidates.map((x) => (
              <li key={x.transaction_id}>
                {shortDay(x.txn_date)} · {x.account_name} · <span className="num">{money(x.amount)}</span> ·{" "}
                {x.description}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">Pair them on People &amp; transfers.</p>
        </div>
      )}
      {c && c.invoices.length > 0 && (
        <div>
          <p className="text-muted">
            {c.invoices.some((i) => i.linked)
              ? "The invoice it paid:"
              : "Invoices of this amount around its day:"}
          </p>
          <ul className="mt-1 space-y-1">
            {c.invoices.map((i) => (
              <li key={i.invoice_id} className="flex flex-wrap items-center gap-2">
                <span>
                  <strong>{i.issuer_name}</strong> · {shortDay(i.issue_date)} ·{" "}
                  <span className="num">{money(i.total)}</span>
                  {i.products.length > 0 && <span className="text-muted"> · {i.products.join(", ")}</span>}
                </span>
                {i.linked ? (
                  <span className="pill pill-good">Paid by this line</span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary h-7 px-2 text-xs"
                    disabled={link.isPending}
                    onClick={() => link.mutate(i.invoice_id)}
                  >
                    This is the one
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {c?.rule && (
        <p>
          <span className="text-muted">Rule for lines like it: </span>“{c.rule.pattern}”
          {c.rule.amount_min ? ` at ${money(c.rule.amount_min)}` : ""} → {c.rule.category_path ?? "—"}{" "}
          <Link to="/settings#rules" className="text-primary underline">
            Edit rules
          </Link>
        </p>
      )}
      {c &&
        !c.rule &&
        !c.same_amount.length &&
        !c.invoices.length &&
        !c.transfer_candidates.length &&
        !c.purpose?.unusual && <p className="text-muted">Nothing else matches this line yet.</p>}
    </section>
  );
}

type PartRow = { amount: string; categoryId: number | "" };

function SplitEditor({ t }: { t: Txn }) {
  const invalidate = useInvalidate();
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
  const size = Math.abs(num(t.amount));
  const sign = num(t.amount) < 0 ? -1 : 1;
  const [rows, setRows] = useState<PartRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const split = useMutation({
    mutationFn: (parts: PartRow[]) =>
      splitTransaction(
        t.transaction_id,
        parts.map((p) => ({
          amount: (sign * Number(p.amount)).toFixed(2),
          category_id: Number(p.categoryId),
        })),
      ),
    onSuccess: () => {
      setRows(null);
      invalidate();
    },
    onError: (e: Error) => setError(e.message),
  });
  const unsplit = useMutation({
    mutationFn: () => removeSplit(t.transaction_id),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  });

  if (!rows)
    return (
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() =>
            setRows([
              { amount: size.toFixed(2), categoryId: t.category_id ?? "" },
              { amount: "", categoryId: "" },
            ])
          }
        >
          {t.parts ? "Change the split" : "Split across categories"}
        </button>
        {t.parts > 0 && (
          <button
            type="button"
            className="btn btn-danger"
            disabled={unsplit.isPending}
            onClick={() => unsplit.mutate()}
          >
            Remove split
          </button>
        )}
        {error && <span className="text-danger-ink">{error}</span>}
      </div>
    );

  const assigned = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const left = Math.round((size - assigned) * 100) / 100;
  const ready = left === 0 && rows.every((r) => Number(r.amount) > 0 && r.categoryId !== "");
  const set = (i: number, patch: Partial<PartRow>) =>
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <form
      className="space-y-3 rounded-2xl border border-line p-3"
      aria-label={`Split ${t.description}`}
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        if (ready) split.mutate(rows);
      }}
    >
      <p className="text-sm text-muted">
        Split <span className="num text-ink">{money(size)}</span> across categories. The line stays as loaded;
        its parts count instead.
      </p>
      {rows.map((r, i) => (
        <div key={i} className="grid grid-cols-[8rem_minmax(0,1fr)_auto] items-end gap-2">
          <label>
            <span className="label">Part {i + 1}</span>
            <input
              className="field num"
              type="number"
              min="0.01"
              step="0.01"
              inputMode="decimal"
              value={r.amount}
              onChange={(e) => set(i, { amount: e.target.value })}
            />
          </label>
          <CategoryPicker
            label={`Category of part ${i + 1}`}
            value={r.categoryId}
            onChange={(id) => set(i, { categoryId: id })}
            groups={groups}
          />
          <button
            type="button"
            className="btn btn-quiet h-11 px-3"
            aria-label={`Remove part ${i + 1}`}
            disabled={rows.length <= 2}
            onClick={() => setRows(rows.filter((_, j) => j !== i))}
          >
            ✕
          </button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => setRows([...rows, { amount: left > 0 ? left.toFixed(2) : "", categoryId: "" }])}
        >
          Add a part
        </button>
        <span className={`num ${left === 0 ? "text-good-ink" : "text-attention-ink"}`} aria-live="polite">
          {left === 0
            ? "Fully assigned"
            : left > 0
              ? `${money(left)} left to assign`
              : `${money(-left)} too much`}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn btn-secondary" disabled={!ready || split.isPending}>
          Save split
        </button>
        <button type="button" className="btn btn-quiet" onClick={() => setRows(null)}>
          Cancel
        </button>
      </div>
      {error && <p className="text-danger-ink">{error}</p>}
    </form>
  );
}
