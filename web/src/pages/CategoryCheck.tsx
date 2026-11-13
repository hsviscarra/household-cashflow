import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchCategories, fetchTransactions, statementPageUrl, updateTransaction, type Txn } from "../api";
import CategoryPicker from "../components/CategoryPicker";
import DataTable, { type Column } from "../components/DataTable";
import { addMonths, localToday, money, monthLong, num } from "../money";
import { personParam, usePerson } from "../prefs";

// Transactions → By category (ADR-065): every category of a period with its lines, to check them
// and move the wrong ones, one at a time or several at once. Covers every kind of line (income,
// savings, debt payments, transfers), not only spending.

const KIND_ORDER: Record<string, number> = {
  income: 0,
  expense: 1,
  refund: 1,
  fee_interest: 1,
  savings: 2,
  debt_payment: 3,
  transfer: 4,
};
const KIND_NAME = ["Income", "Spending", "Savings", "Debt payments", "Transfers"];
const NONE = "No category yet";
const PERIODS: [number, string][] = [
  [1, "Month"],
  [3, "3 months"],
  [12, "12 months"],
];

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

type Row = { path: string; kind: number; lines: Txn[]; total: number };

export default function CategoryCheckPage() {
  const [params, setParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(params.get("month") ?? "")
    ? params.get("month")!
    : addMonths(`${localToday().slice(0, 7)}-01`, -1).slice(0, 7);
  const months = [3, 12].includes(Number(params.get("months"))) ? Number(params.get("months")) : 1;
  const chosen = params.get("c");
  const [person, , ready] = usePerson();
  const q = useQuery({
    queryKey: ["transactions", month, person, months, null],
    queryFn: () => fetchTransactions(`${month}-01`, personParam(person), { months }),
    enabled: ready,
  });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v === null) next.delete(k);
    else next.set(k, v);
    setParams(next, { replace: true });
  };

  const rows = useMemo(() => {
    const by = new Map<string, Row>();
    for (const t of q.data ?? []) {
      if (t.parts) continue; // its parts count instead
      const path = t.category_path ?? NONE;
      const r = by.get(path) ?? {
        path,
        kind: t.category_path ? (KIND_ORDER[t.type] ?? 1) : -1,
        lines: [],
        total: 0,
      };
      r.lines.push(t);
      r.total += num(t.amount);
      by.set(path, r);
    }
    return [...by.values()].sort((a, b) => a.kind - b.kind || Math.abs(b.total) - Math.abs(a.total));
  }, [q.data]);
  const current = rows.find((r) => r.path === chosen) ?? rows[0];

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight">By category</h1>
          <p className="mt-1 max-w-3xl text-muted">
            Every category with its lines, income and transfers included. Pick one on the left, check its
            lines, and move the ones that don't belong: one at a time, or tick several and move them together.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div role="radiogroup" aria-label="Period" className="flex rounded-[10px] bg-surface p-1 text-sm">
            {PERIODS.map(([n, name]) => (
              <button
                key={n}
                role="radio"
                aria-checked={months === n}
                onClick={() => set("months", n === 1 ? null : String(n))}
                className={`rounded-lg px-3 py-1.5 font-semibold ${months === n ? "bg-ground shadow-sm" : "text-muted"}`}
              >
                {name}
              </button>
            ))}
          </div>
          <label>
            <span className="label">{months === 1 ? "Month" : "Up to"}</span>
            <input
              type="month"
              className="field w-44"
              value={month}
              onChange={(e) => e.target.value && set("month", e.target.value)}
            />
          </label>
        </div>
      </header>
      {q.error && <p className="text-danger-ink">{(q.error as Error).message}</p>}
      {!q.data && !q.error && <p className="text-muted">Loading…</p>}
      {q.data && rows.length === 0 && <p className="card p-6 text-muted">No lines in this period.</p>}
      {current && (
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <nav
            aria-label="Categories"
            className="card max-h-[75vh] overflow-y-auto p-2 lg:sticky lg:top-6 lg:self-start"
          >
            {[-1, 0, 1, 2, 3, 4].map((k) => {
              const list = rows.filter((r) => r.kind === k);
              if (!list.length) return null;
              return (
                <div key={k} className="mb-2">
                  <p className="label px-2 pt-2">{k === -1 ? "To do" : KIND_NAME[k]}</p>
                  <ul>
                    {list.map((r) => {
                      const on = r.path === current.path;
                      return (
                        <li key={r.path}>
                          <button
                            type="button"
                            aria-current={on ? "true" : undefined}
                            onClick={() => set("c", r.path)}
                            className={`flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm ${
                              on ? "bg-nav-active font-semibold text-nav-active-ink" : "hover:bg-surface"
                            } ${r.kind === -1 ? "text-attention-ink" : ""}`}
                          >
                            <span className="min-w-0 truncate">{r.path}</span>
                            <span className="num shrink-0 text-xs">
                              {money(Math.abs(r.total))} · {r.lines.length}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </nav>
          <Lines key={current.path} row={current} groups={cats.data ?? []} />
        </div>
      )}
    </section>
  );
}

// The columns shown until a person chooses their own (ADR-091).
const LINE_DEFAULTS = ["date", "account", "amount", "move"];

function Lines({ row, groups }: { row: Row; groups: Parameters<typeof CategoryPicker>[0]["groups"] }) {
  const qc = useQueryClient();
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [note, setNote] = useState<string | null>(null);
  const move = useMutation({
    mutationFn: async ({ ids, category_id }: { ids: number[]; category_id: number }) => {
      for (const id of ids) await updateTransaction(id, { category_id });
      return ids.length;
    },
    onSuccess: (n) => {
      setTicked(new Set());
      setNote(`Moved ${n} line${n === 1 ? "" : "s"}.`);
      ["transactions", "cashflow", "spending", "todo", "review"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      );
    },
    onError: (e: Error) => setNote(e.message),
  });
  const all = row.lines.map((t) => t.transaction_id);
  const toggle = (id: number) =>
    setTicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const columns: Column<Txn>[] = [
    {
      id: "tick",
      label: "Tick",
      fixed: true,
      header: (
        <input
          type="checkbox"
          aria-label="Tick every line"
          checked={ticked.size === all.length && all.length > 0}
          onChange={(e) => setTicked(e.target.checked ? new Set(all) : new Set())}
        />
      ),
      cell: (t) => (
        <input
          type="checkbox"
          aria-label={`Tick ${t.description}`}
          checked={ticked.has(t.transaction_id)}
          onChange={() => toggle(t.transaction_id)}
        />
      ),
    },
    {
      id: "description",
      label: "Description",
      fixed: true,
      sort: (t) => t.description,
      group: (t) => t.merchant ?? t.description,
      cell: (t) => (
        <span className="block max-w-80 truncate" title={t.description}>
          {t.description}
          {t.statement_file_id && (
            <>
              {" "}
              <a
                className="text-xs text-primary underline"
                target="_blank"
                rel="noreferrer"
                href={statementPageUrl(t.statement_file_id, null)}
              >
                statement
              </a>
            </>
          )}
        </span>
      ),
    },
    {
      id: "date",
      label: "Date",
      sort: (t) => t.txn_date,
      group: (t) => monthLong(`${t.txn_date.slice(0, 7)}-01`),
      cell: (t) => <span className="whitespace-nowrap">{day(t.txn_date)}</span>,
    },
    {
      id: "account",
      label: "Account",
      sort: (t) => t.account_name ?? t.source,
      group: (t) => t.account_name ?? t.source,
      cell: (t) => <span className="text-muted">{t.account_name ?? t.source}</span>,
    },
    {
      id: "who",
      label: "Who",
      sort: (t) => t.person ?? "",
      group: (t) => t.person ?? "Nobody",
      cell: (t) => t.person ?? "",
    },
    {
      id: "month",
      label: "Counts in",
      sort: (t) => t.cash_month,
      group: (t) => monthLong(t.cash_month),
      cell: (t) => <span className="whitespace-nowrap">{monthLong(t.cash_month)}</span>,
    },
    { id: "note", label: "Note", cell: (t) => <span className="text-muted">{t.notes ?? ""}</span> },
    {
      id: "amount",
      label: "Amount",
      align: "right",
      sort: (t) => num(t.amount),
      total: (t) => num(t.amount),
      cell: (t) => <span className={num(t.amount) > 0 ? "text-flow-in" : ""}>{money(t.amount)}</span>,
    },
    {
      id: "move",
      label: "Move to",
      cell: (t) => (
        <div className="w-56">
          <CategoryPicker
            label={`Move ${t.description} to`}
            hideLabel
            groups={groups}
            value=""
            placeholder="Move to…"
            onChange={(id) => id !== "" && move.mutate({ ids: [t.transaction_id], category_id: id })}
          />
        </div>
      ),
    },
  ];
  return (
    <section aria-label={row.path} className="card min-w-0 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-bold">{row.path}</h2>
          <p className="num text-sm text-muted">
            {row.lines.length} lines · {money(row.total)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm">
            {ticked.size ? `Move ${ticked.size} ticked to` : "Tick lines to move them together"}
          </span>
          {ticked.size > 0 && (
            <div className="w-64">
              <CategoryPicker
                label="Move ticked lines to"
                hideLabel
                groups={groups}
                value=""
                placeholder="Choose a category…"
                onChange={(id) => id !== "" && move.mutate({ ids: [...ticked], category_id: id })}
              />
            </div>
          )}
        </div>
      </div>
      {note && (
        <p role="status" className="mt-3 rounded-[10px] bg-good-bg p-2 text-sm text-good-ink">
          {note}
        </p>
      )}
      <div className="mt-3">
        <DataTable
          table="category-lines"
          caption={`Lines in ${row.path}`}
          columns={columns}
          rows={row.lines}
          rowKey={(t) => t.transaction_id}
          defaults={LINE_DEFAULTS}
          defaultSort={{ id: "date", dir: "desc" }}
        />
      </div>
    </section>
  );
}
