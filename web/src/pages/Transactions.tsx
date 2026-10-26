import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  fetchCategories,
  fetchHistory,
  fetchTransactions,
  removeSplit,
  splitTransaction,
  unlinkTransfer,
  updateTransaction,
  type Txn,
} from "../api";
import { categoryOptions } from "../categories";
import { money, monthLong, num, showAmount } from "../money";

type Option = { id: number; label: string };

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
};

function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** Lines that count: a split line counts through its parts. */
export const counted = (t: Txn) => !t.parts;

export default function TransactionsPage() {
  const [params, setParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : thisMonth();
  const { data, error } = useQuery({
    queryKey: ["transactions", month],
    queryFn: () => fetchTransactions(`${month}-01`),
  });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [open, setOpen] = useState<number | null>(null);
  const options = cats.data ? categoryOptions(cats.data) : [];

  const out = (data ?? []).filter((t) => counted(t) && num(t.amount) < 0 && t.type !== "transfer");
  const totalOut = out.reduce((s, t) => s - num(t.amount), 0);
  const needing = (data ?? []).filter((t) => counted(t) && !t.category_id && t.source === "statement").length;
  // Parts are listed right under the line they split.
  const rows = data ? ordered(data) : [];

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">Transactions</h1>
      <p className="mt-2 text-lg text-muted">
        Every loaded line for a month. Edit a category or split a charge; every change is kept in its history.
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-4">
        <label>
          <span className="label">Month</span>
          <input
            type="month"
            className="field w-48"
            value={month}
            onChange={(e) => e.target.value && setParams({ month: e.target.value })}
          />
        </label>
        {data && (
          <p className="pb-2 text-muted">
            {monthLong(`${month}-01`)}: {data.length} lines, <span className="num">{money(totalOut)}</span>{" "}
            out (card payments and transfers excluded)
          </p>
        )}
      </div>

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
          {monthLong(`${month}-01`)} is covered by the Excel history, so the totals on the Overview use the
          workbook. The statement lines below are kept for reference and don’t count twice.
        </p>
      )}
      {data && !data.length && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">
          Nothing loaded for {monthLong(`${month}-01`)} yet. Upload and approve a statement on the Import
          page.
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
              <EditToggle t={t} open={open} setOpen={setOpen} />
              {open === t.transaction_id && (
                <div className="mt-3">
                  <TxnEditor t={t} options={options} onDone={() => setOpen(null)} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {data && data.length > 0 && (
        <div className="mt-6 hidden overflow-x-auto rounded-2xl border border-line md:block">
          <table className="w-full text-sm">
            <caption className="sr-only">Transactions in {monthLong(`${month}-01`)}</caption>
            <thead className="bg-surface text-muted">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Date
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Description
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Account
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Who
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Category
                </th>
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
                    <td className="num whitespace-nowrap px-4 py-2">{day(t.txn_date)}</td>
                    <td className={`px-4 py-2 ${t.parent_transaction_id ? "pl-8" : ""}`}>
                      {t.parent_transaction_id && <span aria-hidden>↳ </span>}
                      <span className={t.parts ? "line-through" : ""}>{t.description}</span>
                      {t.notes && <span className="block text-xs text-muted">{t.notes}</span>}
                    </td>
                    <td className="px-4 py-2 text-muted">
                      {t.account_name ?? SOURCE_LABEL[t.source] ?? t.source}
                    </td>
                    <td className="px-4 py-2">{t.person}</td>
                    <td className="px-4 py-2">
                      <CategoryCell t={t} />
                    </td>
                    <td className={`num px-4 py-2 text-right ${t.parts ? "line-through" : ""}`}>
                      {showAmount(t.amount)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <EditToggle t={t} open={open} setOpen={setOpen} />
                    </td>
                  </tr>
                  {open === t.transaction_id && (
                    <tr>
                      <td colSpan={7} className="bg-surface px-4 py-4">
                        <TxnEditor t={t} options={options} onDone={() => setOpen(null)} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
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

function TxnEditor({ t, options, onDone }: { t: Txn; options: Option[]; onDone: () => void }) {
  const invalidate = useInvalidate();
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
          <label>
            <span className="label">Category</span>
            <select
              className="field"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">Choose a category</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
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

      <UnlinkTransfer t={t} />
      {!t.parent_transaction_id && !t.transfer_group_id && <SplitEditor t={t} options={options} />}

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

type PartRow = { amount: string; categoryId: number | "" };

function SplitEditor({ t, options }: { t: Txn; options: Option[] }) {
  const invalidate = useInvalidate();
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
          <label>
            <span className="label">Category of part {i + 1}</span>
            <select
              className="field"
              value={r.categoryId}
              onChange={(e) => set(i, { categoryId: e.target.value ? Number(e.target.value) : "" })}
            >
              <option value="">Choose a category</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
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
