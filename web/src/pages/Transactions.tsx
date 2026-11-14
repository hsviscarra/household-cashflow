import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchCategories, fetchPeople, fetchTransactions, updateTransaction, type Owner } from "../api";
import CategoryPicker from "../components/CategoryPicker";
import DataTable from "../components/DataTable";
import { PersonNote } from "../components/Personalize";
import { addMonths, money, monthLong, num, showAmount } from "../money";
import { personParam, usePerson, useTableLayout } from "../prefs";
import {
  thisMonth,
  OWNERS,
  DEFAULT_COLUMNS,
  type Filters,
  group,
  keep,
  counted,
  toCsv,
  download,
  ordered,
} from "./transactions/shared";
import { TickedTotals, ViewTabs } from "./transactions/Cells";
import { txnColumns } from "./transactions/columns";
import { FilterBar } from "./transactions/FilterBar";
import { TxnList } from "./transactions/TxnList";
import { TxnEditor } from "./transactions/TxnEditor";

export { LineKnown } from "./transactions/LineKnown";

export { matches, learnedMessage, type Filters, keep, counted, toCsv } from "./transactions/shared";

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
  // The note shows under the description while its own column is hidden.
  const [layout] = useTableLayout("transactions", ["note"], DEFAULT_COLUMNS);
  const show = (c: string) => layout.columns.includes(c);
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
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [open, setOpen] = useState<number | null>(null);
  // Ticked lines (ADR-093): their totals show above the table and they can be categorized together.
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const qc = useQueryClient();
  const bulk = useMutation({
    mutationFn: async ({ ids, ...change }: { ids: number[]; category_id?: number; person?: Owner }) => {
      for (const id of ids) await updateTransaction(id, change);
    },
    onSuccess: () => {
      setTicked(new Set());
      ["transactions", "cashflow", "spending", "todo", "review"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      );
    },
  });

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

  const columns = txnColumns(show, names, open, setOpen);

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

      <FilterBar
        month={month}
        months={months}
        f={f}
        min={params.get("min") ?? ""}
        max={params.get("max") ?? ""}
        accounts={accounts}
        groups={groups}
        setParam={setParam}
      />
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
          <TxnList rows={rows} names={names} open={open} setOpen={setOpen} />
        </ul>
      )}
      {data && data.length > 0 && (
        <div className="mt-6 hidden md:block">
          <DataTable
            table="transactions"
            caption={`Transactions in ${period}`}
            columns={columns}
            rows={rows}
            rowKey={(t) => t.transaction_id}
            defaults={DEFAULT_COLUMNS}
            rowClass={(t) => (t.parts ? "text-muted" : "")}
            expanded={(t) =>
              open === t.transaction_id ? <TxnEditor t={t} onDone={() => setOpen(null)} /> : null
            }
            select={{
              ticked,
              onChange: (next) => setTicked(next as Set<number>),
              name: (t) => t.description,
              summary: (lines) => <TickedTotals lines={lines.filter(counted)} />,
              actions: (lines) => (
                <span className="flex items-center gap-2">
                  Categorize as
                  <span className="w-56">
                    <CategoryPicker
                      label="Category for the ticked lines"
                      hideLabel
                      groups={cats.data ?? []}
                      value=""
                      placeholder="Choose a category"
                      onChange={(id) =>
                        id !== "" && bulk.mutate({ ids: lines.map((t) => t.transaction_id), category_id: id })
                      }
                    />
                  </span>
                  <label className="flex items-center gap-2">
                    Whose
                    <select
                      className="field !w-32"
                      aria-label="Who the ticked lines belong to"
                      value=""
                      onChange={(e) =>
                        e.target.value &&
                        bulk.mutate({
                          ids: lines.map((t) => t.transaction_id),
                          person: e.target.value as Owner,
                        })
                      }
                    >
                      <option value="">Choose</option>
                      {OWNERS.map((o) => (
                        <option key={o}>{o}</option>
                      ))}
                    </select>
                  </label>
                  {bulk.isPending && <span className="text-muted">Saving…</span>}
                  {bulk.error && (
                    <span role="alert" className="text-danger-ink">
                      {(bulk.error as Error).message}
                    </span>
                  )}
                </span>
              ),
            }}
          />
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
