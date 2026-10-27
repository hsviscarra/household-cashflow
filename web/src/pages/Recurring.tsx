import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  changeTemplateAmount,
  copyMonth,
  createFromExcel,
  createTemplate,
  deleteTemplate,
  editEntry,
  fetchAccounts,
  fetchCategories,
  fetchEntry,
  fetchExcelRows,
  fetchRecurringGrid,
  fetchTemplates,
  generateMonth,
  linkLine,
  matchRecurring,
  unlinkLine,
  updateTemplate,
  type GridCell,
  type GridRow,
  type RecurringTemplate,
  type TemplateType,
  type Txn,
} from "../api";
import { categoryOptions } from "../categories";
import { money, monthLong, monthName, monthShort, num, showAmount } from "../money";

type Notify = (message: string, tone?: "good" | "bad") => void;
type Option = { id: number; label: string };
type Selected =
  { kind: "cell"; template: number; month: string } | { kind: "template"; template: number } | null;

const TYPES: { id: TemplateType; label: string }[] = [
  { id: "expense", label: "Expense" },
  { id: "income", label: "Income" },
  { id: "debt_payment", label: "Loan or card payment" },
  { id: "savings", label: "Savings or investing" },
  { id: "transfer", label: "Transfer" },
  { id: "fee_interest", label: "Fees and interest" },
];
const isIncome = (t: string) => t === "income";
const thisMonth = () => new Date().toISOString().slice(0, 7);
const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** What a cell counts as: the matched lines, else the expected amount; skipped months count 0. */
export function cellValue(c: GridCell): number {
  if (c.status === "matched") return num(c.actual);
  if (c.status === "planned") return num(c.expected);
  return 0;
}

/** Monthly totals of the grid: money in, money out (positive) and what is left. */
export function totals(rows: GridRow[]) {
  const n = rows[0]?.cells.length ?? 12;
  const income = Array<number>(n).fill(0);
  const out = Array<number>(n).fill(0);
  for (const r of rows)
    r.cells.forEach((c, i) => {
      const v = cellValue(c);
      if (v > 0) income[i] += v;
      else out[i] -= v;
    });
  return { income, out, left: income.map((v, i) => v - out[i]) };
}

function useRefresh() {
  const qc = useQueryClient();
  return () =>
    ["recurring", "transactions", "cashflow"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}

export default function RecurringPage() {
  const [params, setParams] = useSearchParams();
  const now = thisMonth();
  const year = Number(params.get("year")) || Number(now.slice(0, 4));
  const grid = useQuery({ queryKey: ["recurring", "grid", year], queryFn: () => fetchRecurringGrid(year) });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const templates = useQuery({ queryKey: ["recurring", "templates"], queryFn: fetchTemplates });
  const [selected, setSelected] = useState<Selected>(null);
  const [panel, setPanel] = useState<"new" | "excel" | "copy" | null>(null);
  const [month, setMonth] = useState(now.startsWith(String(year)) ? now : `${year}-01`);
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });
  const refresh = useRefresh();

  const generate = useMutation({
    mutationFn: () => generateMonth(`${month}-01`),
    onSuccess: (r) => {
      refresh();
      notify(
        r.count
          ? `${monthLong(`${month}-01`)}: ${r.count} recurring ${r.count === 1 ? "item" : "items"} generated.`
          : `${monthLong(`${month}-01`)} already has every recurring item.`,
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const rematch = useMutation({
    mutationFn: matchRecurring,
    onSuccess: (r) => {
      refresh();
      notify(
        r.count ? `Linked ${r.count} more ${r.count === 1 ? "line" : "lines"}.` : "No new lines to link.",
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });

  const options = cats.data ? categoryOptions(cats.data) : [];
  const rows = grid.data?.rows ?? [];
  const income = rows.filter((r) => isIncome(r.type));
  const expenses = rows.filter((r) => !isIncome(r.type));
  const t = totals(rows);
  const mi = Number(month.slice(5, 7)) - 1;
  const inMonth = rows.map((r) => r.cells[mi]).filter((c) => c && c.status !== "none");
  const matched = inMonth.filter((c) => c.status === "matched").length;
  const selRow = selected ? rows.find((r) => r.template_id === selected.template) : undefined;
  const selTemplate = selected ? templates.data?.find((x) => x.template_id === selected.template) : undefined;

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {rows.length
          ? `${monthLong(`${month}-01`)}: ${matched} of ${inMonth.length} recurring items paid`
          : "Recurring"}
      </h1>
      <p className="mt-2 text-lg text-muted">
        Salary, rent, fees and payments that repeat each month: what you expect, and the lines that paid it.
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-3">
        <div className="flex gap-1" role="group" aria-label="Year">
          <button className="btn btn-quiet h-11 px-3" onClick={() => setParams({ year: String(year - 1) })}>
            ← {year - 1}
          </button>
          <span className="flex h-11 items-center px-3 font-display text-xl font-bold">{year}</span>
          <button className="btn btn-quiet h-11 px-3" onClick={() => setParams({ year: String(year + 1) })}>
            {year + 1} →
          </button>
        </div>
        <label>
          <span className="label">Month</span>
          <input
            type="month"
            className="field w-48"
            value={month}
            onChange={(e) => {
              if (!e.target.value) return;
              setMonth(e.target.value);
              if (!e.target.value.startsWith(String(year))) setParams({ year: e.target.value.slice(0, 4) });
            }}
          />
        </label>
        <button
          className={`btn ${rows.length && panel !== "excel" ? "btn-primary" : "btn-secondary"}`}
          disabled={generate.isPending || !rows.length}
          onClick={() => generate.mutate()}
        >
          {generate.isPending ? "Generating…" : `Generate ${monthName(mi + 1)}`}
        </button>
        <button
          className="btn btn-secondary"
          disabled={!rows.length}
          onClick={() => setPanel(panel === "copy" ? null : "copy")}
        >
          Copy {monthShort(`${month}-01`)} forward
        </button>
        <button className="btn btn-secondary" onClick={() => setPanel(panel === "new" ? null : "new")}>
          New template
        </button>
        <button className="btn btn-quiet" onClick={() => setPanel(panel === "excel" ? null : "excel")}>
          From the {year} sheet
        </button>
        <button
          className="btn btn-quiet"
          disabled={rematch.isPending || !rows.length}
          onClick={() => rematch.mutate()}
        >
          Match lines again
        </button>
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

      {panel === "copy" && <CopyForm month={month} onDone={() => setPanel(null)} notify={notify} />}
      {panel === "new" && (
        <TemplateForm
          options={options}
          accounts={accounts.data ?? []}
          month={month}
          onDone={() => setPanel(null)}
          notify={notify}
        />
      )}
      {panel === "excel" && <ExcelPicker year={year} onDone={() => setPanel(null)} notify={notify} />}

      {grid.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the recurring items: {(grid.error as Error).message}
        </p>
      )}
      {!grid.data && !grid.error && <p className="mt-6 text-muted">Loading the recurring items…</p>}
      {grid.data && !rows.length && panel === null && (
        <div className="mt-6 rounded-2xl bg-info-bg px-5 py-4">
          <p>
            No recurring items in {year} yet. Start from the rows of your Cash Flow sheet, or add one template
            at a time.
          </p>
          <button className="btn btn-primary mt-3" onClick={() => setPanel("excel")}>
            Choose rows from the {year} sheet
          </button>
        </div>
      )}

      {rows.length > 0 && grid.data && (
        <>
          <div className="mt-6 overflow-x-auto rounded-2xl border border-line">
            <table className="w-full min-w-[960px] text-[13px]">
              <caption className="sr-only">Recurring items in {year}, by month</caption>
              <thead className="bg-surface text-muted">
                <tr>
                  <th scope="col" className="sticky left-0 w-32 bg-surface px-3 py-2 text-left font-semibold">
                    Item
                  </th>
                  {grid.data.months.map((m) => (
                    <th
                      key={m}
                      scope="col"
                      className={`px-1.5 py-2 text-right font-semibold ${m.startsWith(month) ? "text-ink underline decoration-2 underline-offset-4" : ""}`}
                    >
                      {monthShort(m)}
                      {grid.data.excel_months.includes(m) && (
                        <span className="block text-xs font-normal">sheet</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <Block title="Income" rows={income} selected={selected} onSelect={setSelected} />
              <Block title="Expenses" rows={expenses} selected={selected} onSelect={setSelected} />
              <tfoot className="border-t-2 border-line font-semibold">
                <TotalRow label="Money in" values={t.income} />
                <TotalRow label="Money out" values={t.out} />
                <TotalRow label="Left" values={t.left} signedValues />
              </tfoot>
            </table>
          </div>
          <p className="mt-2 text-sm text-muted">
            <span className="text-ink">1,234.00</span> paid (lines linked) ·{" "}
            <span className="italic">1,234.00</span> expected · <span aria-hidden>•</span> changed for that
            month only · “—” not generated yet. Select a cell or an item to change it.
          </p>
        </>
      )}

      {selected?.kind === "cell" && selRow && (
        <CellPanel
          key={`${selected.template}-${selected.month}`}
          row={selRow}
          month={selected.month}
          template={selTemplate}
          notify={notify}
          onClose={() => setSelected(null)}
        />
      )}
      {selected?.kind === "template" && selTemplate && (
        <TemplateEditor
          key={selTemplate.template_id}
          t={selTemplate}
          options={options}
          accounts={accounts.data ?? []}
          notify={notify}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}

function Block({
  title,
  rows,
  selected,
  onSelect,
}: {
  title: string;
  rows: GridRow[];
  selected: Selected;
  onSelect: (s: Selected) => void;
}) {
  if (!rows.length) return null;
  let group = "";
  return (
    <tbody className="divide-y divide-line">
      <tr>
        <th
          colSpan={13}
          scope="rowgroup"
          className="bg-ground px-3 pb-1 pt-4 text-left font-display text-base font-bold"
        >
          <span className="sticky left-3">{title}</span>
        </th>
      </tr>
      {rows.map((r) => {
        const header = r.group !== group;
        group = r.group;
        return (
          <Fragment key={r.template_id}>
            {header && (
              <tr>
                <td
                  colSpan={13}
                  className="px-3 pt-2 text-xs font-semibold uppercase tracking-wide text-muted"
                >
                  <span className="sticky left-3">{r.group}</span>
                </td>
              </tr>
            )}
            <tr className={r.is_active ? "" : "text-muted"}>
              <th scope="row" className="sticky left-0 bg-ground px-3 py-1.5 text-left font-medium">
                <button
                  className="text-left underline-offset-2 hover:underline"
                  aria-pressed={selected?.kind === "template" && selected.template === r.template_id}
                  onClick={() => onSelect({ kind: "template", template: r.template_id })}
                >
                  {r.name}
                </button>
              </th>
              {r.cells.map((c) => (
                <td key={c.month} className="px-0.5 py-1 text-right">
                  <CellButton
                    row={r}
                    c={c}
                    active={
                      selected?.kind === "cell" &&
                      selected.template === r.template_id &&
                      selected.month === c.month
                    }
                    onClick={() => onSelect({ kind: "cell", template: r.template_id, month: c.month })}
                  />
                </td>
              ))}
            </tr>
          </Fragment>
        );
      })}
    </tbody>
  );
}

const STATUS_WORD: Record<GridCell["status"], string> = {
  matched: "paid",
  planned: "expected",
  skipped: "skipped",
  not_generated: "not generated",
  none: "",
};

function CellButton({
  row,
  c,
  active,
  onClick,
}: {
  row: GridRow;
  c: GridCell;
  active: boolean;
  onClick: () => void;
}) {
  if (c.status === "none") return <span className="sr-only">none</span>;
  const shown =
    c.status === "matched"
      ? money(Math.abs(num(c.actual)))
      : c.status === "planned"
        ? money(Math.abs(num(c.expected)))
        : c.status === "skipped"
          ? "skipped"
          : "—";
  const look =
    c.status === "matched" ? "text-ink" : c.status === "planned" ? "italic text-muted" : "text-xs text-muted";
  return (
    <button
      className={`num w-full whitespace-nowrap rounded-lg px-1 py-1 text-right hover:bg-surface ${active ? "bg-info-bg" : ""} ${look}`}
      aria-label={`${row.name}, ${monthLong(c.month)}: ${shown === "—" ? "" : `${shown}, `}${STATUS_WORD[c.status]}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {c.is_override && c.status !== "matched" && <span aria-hidden>• </span>}
      {shown}
    </button>
  );
}

function TotalRow({
  label,
  values,
  signedValues,
}: {
  label: string;
  values: number[];
  signedValues?: boolean;
}) {
  return (
    <tr>
      <th scope="row" className="sticky left-0 bg-ground px-3 py-1.5 text-left">
        {label}
      </th>
      {values.map((v, i) => (
        <td key={i} className="num whitespace-nowrap px-1.5 py-1.5 text-right">
          {signedValues ? (v < 0 ? `−${money(-v)}` : money(v)) : money(v)}
        </td>
      ))}
    </tr>
  );
}

// ---------------------------------------------------------------- one cell
function CellPanel({
  row,
  month,
  template,
  notify,
  onClose,
}: {
  row: GridRow;
  month: string;
  template: RecurringTemplate | undefined;
  notify: Notify;
  onClose: () => void;
}) {
  const refresh = useRefresh();
  const qc = useQueryClient();
  const cell = row.cells.find((c) => c.month === month)!;
  const entry = useQuery({
    queryKey: ["recurring", "entry", cell.entry_id],
    queryFn: () => fetchEntry(cell.entry_id!),
    enabled: cell.entry_id != null,
  });
  const e = entry.data;
  const [amount, setAmount] = useState("");
  const [from, setFrom] = useState("");
  const done = (message: string) => {
    refresh();
    qc.invalidateQueries({ queryKey: ["recurring", "entry", cell.entry_id] });
    notify(message);
  };
  const fail = (err: Error) => notify(err.message, "bad");
  const edit = useMutation({
    mutationFn: (b: Parameters<typeof editEntry>[1]) => editEntry(cell.entry_id!, b),
    onSuccess: (r) =>
      done(
        r.status === "skipped"
          ? `${row.name} skipped in ${monthLong(month)}.`
          : `${row.name}, ${monthLong(month)}: ${money(Math.abs(num(r.amount)))} expected.`,
      ),
    onError: fail,
  });
  const change = useMutation({
    mutationFn: () => changeTemplateAmount(row.template_id, month, from),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recurring", "templates"] });
      done(`${row.name}: ${money(from)} from ${monthLong(month)} on.`);
    },
    onError: fail,
  });
  const gen = useMutation({
    mutationFn: () => generateMonth(month),
    onSuccess: () => done(`${monthLong(month)} generated.`),
    onError: fail,
  });
  const link = useMutation({
    mutationFn: (id: number) => linkLine(cell.entry_id!, id),
    onSuccess: () => done("Line linked."),
    onError: fail,
  });
  const unlink = useMutation({
    mutationFn: unlinkLine,
    onSuccess: () => done("Line unlinked."),
    onError: fail,
  });

  return (
    <section
      className="mt-6 rounded-2xl bg-surface p-4 md:p-5"
      aria-label={`${row.name} in ${monthLong(month)}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-bold">
          {row.name} · {monthLong(month)}
        </h2>
        <button className="btn btn-quiet h-9 px-3" onClick={onClose}>
          Close
        </button>
      </div>
      {cell.entry_id == null ? (
        <div className="mt-3">
          <p>
            Not generated yet
            {cell.expected ? `: the template expects ${money(Math.abs(num(cell.expected)))}` : ""}.
          </p>
          <button className="btn btn-secondary mt-3" disabled={gen.isPending} onClick={() => gen.mutate()}>
            Generate {monthLong(month)}
          </button>
        </div>
      ) : !e ? (
        <p className="mt-3 text-muted">Loading…</p>
      ) : (
        <div className="mt-3 grid gap-5 md:grid-cols-2">
          <div className="space-y-4">
            <p>
              Expected <strong className="num">{money(Math.abs(num(e.amount)))}</strong>
              {e.is_override && e.template_amount != null && (
                <> (this month only; the template says {money(Math.abs(num(e.template_amount)))})</>
              )}
              {e.status === "skipped" && <> · skipped</>}. Lines within{" "}
              <span className="num">{money(e.tolerance)}</span> of it are linked.
            </p>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(ev) => {
                ev.preventDefault();
                if (amount) edit.mutate({ amount });
              }}
            >
              <label>
                <span className="label">This month only</span>
                <input
                  className="field num w-36"
                  type="number"
                  min={0.01}
                  step="0.01"
                  inputMode="decimal"
                  value={amount}
                  onChange={(ev) => setAmount(ev.target.value)}
                />
              </label>
              <button className="btn btn-secondary" disabled={!amount || edit.isPending}>
                Save {monthShort(month)}
              </button>
            </form>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(ev) => {
                ev.preventDefault();
                if (from) change.mutate();
              }}
            >
              <label>
                <span className="label">From {monthLong(month)} on</span>
                <input
                  className="field num w-36"
                  type="number"
                  min={0.01}
                  step="0.01"
                  inputMode="decimal"
                  value={from}
                  onChange={(ev) => setFrom(ev.target.value)}
                />
              </label>
              <button className="btn btn-secondary" disabled={!from || change.isPending}>
                Change from {monthShort(month)} on
              </button>
            </form>
            <div className="flex flex-wrap gap-2">
              {e.is_override && (
                <button className="btn btn-quiet" onClick={() => edit.mutate({ reset: true })}>
                  Back to the template amount
                </button>
              )}
              {e.status === "planned" ? (
                <button className="btn btn-quiet" onClick={() => edit.mutate({ status: "skipped" })}>
                  Skip {monthShort(month)} (doesn’t happen)
                </button>
              ) : (
                <button className="btn btn-quiet" onClick={() => edit.mutate({ status: "planned" })}>
                  Expect it again
                </button>
              )}
            </div>
            {template && !template.match_pattern && !template.account_id && (
              <p className="text-sm text-muted">
                Tip: an account or a description pattern on the template makes matching surer when several
                items share a category (the card payments, for example).
              </p>
            )}
          </div>
          <div>
            <h3 className="font-semibold">Lines that paid it</h3>
            {e.lines.length ? (
              <LineList lines={e.lines} action="Unlink" onAction={(id) => unlink.mutate(id)} />
            ) : (
              <p className="mt-1 text-muted">None yet.</p>
            )}
            {e.candidates.length > 0 && (
              <>
                <h3 className="mt-4 font-semibold">Other lines this month</h3>
                <LineList lines={e.candidates.slice(0, 8)} action="Link" onAction={(id) => link.mutate(id)} />
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function LineList({
  lines,
  action,
  onAction,
}: {
  lines: Txn[];
  action: string;
  onAction: (id: number) => void;
}) {
  return (
    <ul className="mt-1 divide-y divide-line">
      {lines.map((ln) => (
        <li key={ln.transaction_id} className="flex items-center justify-between gap-2 py-1.5">
          <span className="min-w-0 flex-1">
            <span className="num">{day(ln.txn_date)}</span>
            <span className="text-muted">
              {" "}
              · {ln.account_name ?? (ln.source === "excel_history" ? "Cash Flow sheet" : "—")}
            </span>
            <span className="block truncate font-mono text-xs">{ln.description}</span>
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <span className="num">{showAmount(ln.amount)}</span>
            <button
              className="btn btn-quiet h-9 px-3 text-sm"
              aria-label={`${action} ${ln.description} on ${day(ln.txn_date)}`}
              onClick={() => onAction(ln.transaction_id)}
            >
              {action}
            </button>
          </span>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- copy
function CopyForm({ month, onDone, notify }: { month: string; onDone: () => void; notify: Notify }) {
  const refresh = useRefresh();
  const next = (m: string, n: number) => {
    const [y, mo] = m.split("-").map(Number);
    const i = y * 12 + mo - 1 + n;
    return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`;
  };
  const [start, setStart] = useState(next(month, 1));
  const [end, setEnd] = useState(next(month, 1));
  const copy = useMutation({
    mutationFn: () => copyMonth({ from_month: `${month}-01`, to_start: `${start}-01`, to_end: `${end}-01` }),
    onSuccess: (r) => {
      refresh();
      notify(`Copied ${monthLong(`${month}-01`)} to ${r.count} ${r.count === 1 ? "cell" : "cells"}.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <form
      className="mt-4 flex flex-wrap items-end gap-3 rounded-2xl bg-surface p-4"
      aria-label="Copy a month"
      onSubmit={(e) => {
        e.preventDefault();
        copy.mutate();
      }}
    >
      <p className="w-full">
        Copy the expected amounts (and skips) of {monthLong(`${month}-01`)} to every month from–to. Months
        with paid lines keep theirs.
      </p>
      <label>
        <span className="label">From</span>
        <input type="month" className="field w-48" value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label>
        <span className="label">To</span>
        <input type="month" className="field w-48" value={end} onChange={(e) => setEnd(e.target.value)} />
      </label>
      <button className="btn btn-secondary" disabled={copy.isPending || !start || !end}>
        Copy to {start === end ? monthLong(`${start}-01`) : "these months"}
      </button>
      <button type="button" className="btn btn-quiet" onClick={onDone}>
        Cancel
      </button>
    </form>
  );
}

// ---------------------------------------------------------------- templates
type Account = { account_id: number; name: string };

function TemplateFields({
  value,
  set,
  options,
  accounts,
}: {
  value: Record<string, string>;
  set: (k: string, v: string) => void;
  options: Option[];
  accounts: Account[];
}) {
  return (
    <>
      <label>
        <span className="label">Category</span>
        <select
          className="field"
          required
          value={value.category_id}
          onChange={(e) => set("category_id", e.target.value)}
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
        <span className="label">Counts as</span>
        <select className="field" value={value.type} onChange={(e) => set("type", e.target.value)}>
          {TYPES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Account (optional)</span>
        <select
          className="field"
          value={value.account_id}
          onChange={(e) => set("account_id", e.target.value)}
        >
          <option value="">Any account</option>
          {accounts.map((a) => (
            <option key={a.account_id} value={a.account_id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Description contains (optional)</span>
        <input
          className="field font-mono"
          maxLength={200}
          value={value.match_pattern}
          onChange={(e) => set("match_pattern", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Tolerance %</span>
        <input
          className="field num"
          type="number"
          min={0}
          max={100}
          step="1"
          value={value.tolerance_pct}
          onChange={(e) => set("tolerance_pct", e.target.value)}
        />
      </label>
    </>
  );
}

function TemplateForm({
  options,
  accounts,
  month,
  onDone,
  notify,
}: {
  options: Option[];
  accounts: Account[];
  month: string;
  onDone: () => void;
  notify: Notify;
}) {
  const refresh = useRefresh();
  const [v, setV] = useState<Record<string, string>>({
    name: "",
    category_id: "",
    type: "expense",
    amount: "",
    start_month: month,
    account_id: "",
    match_pattern: "",
    tolerance_pct: "10",
  });
  const set = (k: string, val: string) => setV({ ...v, [k]: val });
  const save = useMutation({
    mutationFn: () =>
      createTemplate({
        name: v.name.trim(),
        category_id: Number(v.category_id),
        type: v.type as TemplateType,
        amount: v.amount,
        start_month: `${v.start_month}-01`,
        account_id: v.account_id ? Number(v.account_id) : null,
        match_pattern: v.match_pattern.trim() || null,
        tolerance_pct: v.tolerance_pct || "10",
      }),
    onSuccess: (t) => {
      refresh();
      notify(`${t.name} added from ${monthLong(t.start_month)}. Generate a month to expect it.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <form
      className="mt-4 grid gap-3 rounded-2xl bg-surface p-4 md:grid-cols-4"
      aria-label="New template"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <label className="md:col-span-2">
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
        <span className="label">Amount each month</span>
        <input
          className="field num"
          required
          type="number"
          min={0.01}
          step="0.01"
          inputMode="decimal"
          value={v.amount}
          onChange={(e) => set("amount", e.target.value)}
        />
      </label>
      <label>
        <span className="label">First month</span>
        <input
          type="month"
          className="field"
          required
          value={v.start_month}
          onChange={(e) => set("start_month", e.target.value)}
        />
      </label>
      <TemplateFields value={v} set={set} options={options} accounts={accounts} />
      <div className="flex gap-2 md:col-span-4">
        <button
          className="btn btn-secondary"
          disabled={save.isPending || !v.name.trim() || !v.category_id || !v.amount}
        >
          Add template
        </button>
        <button type="button" className="btn btn-quiet" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function TemplateEditor({
  t,
  options,
  accounts,
  notify,
  onClose,
}: {
  t: RecurringTemplate;
  options: Option[];
  accounts: Account[];
  notify: Notify;
  onClose: () => void;
}) {
  const refresh = useRefresh();
  const [v, setV] = useState<Record<string, string>>({
    name: t.name,
    category_id: String(t.category_id),
    type: t.type,
    account_id: t.account_id ? String(t.account_id) : "",
    match_pattern: t.match_pattern ?? "",
    tolerance_pct: String(Number(t.tolerance_pct)),
    end_month: t.end_month?.slice(0, 7) ?? "",
  });
  const set = (k: string, val: string) => setV({ ...v, [k]: val });
  const [confirm, setConfirm] = useState(false);
  const save = useMutation({
    mutationFn: (patch: Parameters<typeof updateTemplate>[1]) => updateTemplate(t.template_id, patch),
    onSuccess: (r) => {
      refresh();
      notify(`${r.name} saved.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const remove = useMutation({
    mutationFn: () => deleteTemplate(t.template_id),
    onSuccess: () => {
      refresh();
      notify(`${t.name} removed, with its months.`);
      onClose();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <section className="mt-6 rounded-2xl bg-surface p-4 md:p-5" aria-label={`Template ${t.name}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-bold">{t.name}</h2>
        <button className="btn btn-quiet h-9 px-3" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="mt-1 text-muted">
        From {monthLong(t.start_month)}
        {t.end_month ? ` to ${monthLong(t.end_month)}` : ""} ·{" "}
        {t.amounts
          .map((a) => `${money(a.amount)} from ${monthShort(a.from_month)} ${a.from_month.slice(0, 4)}`)
          .join(", then ")}
        {t.source === "excel" ? " · from the Cash Flow sheet" : ""}
      </p>
      <form
        className="mt-4 grid gap-3 md:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({
            name: v.name.trim(),
            category_id: Number(v.category_id),
            type: v.type as TemplateType,
            account_id: v.account_id ? Number(v.account_id) : null,
            match_pattern: v.match_pattern.trim() || null,
            tolerance_pct: v.tolerance_pct || "10",
            end_month: v.end_month ? `${v.end_month}-01` : null,
          });
        }}
      >
        <label className="md:col-span-2">
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
          <span className="label">Last month (optional)</span>
          <input
            type="month"
            className="field"
            value={v.end_month}
            onChange={(e) => set("end_month", e.target.value)}
          />
        </label>
        <div />
        <TemplateFields value={v} set={set} options={options} accounts={accounts} />
        <div className="flex flex-wrap gap-2 md:col-span-4">
          <button className="btn btn-secondary" disabled={save.isPending}>
            Save {t.name}
          </button>
          <button
            type="button"
            className="btn btn-quiet"
            onClick={() => save.mutate({ is_active: !t.is_active })}
          >
            {t.is_active ? "Pause it" : "Resume it"}
          </button>
          {!confirm ? (
            <button type="button" className="btn btn-quiet" onClick={() => setConfirm(true)}>
              Remove…
            </button>
          ) : (
            <button
              type="button"
              className="btn bg-danger-bg text-danger-ink"
              onClick={() => remove.mutate()}
            >
              Remove {t.name} and its months
            </button>
          )}
        </div>
      </form>
      <p className="mt-3 text-sm text-muted">
        To change the amount, select a month in the grid: “this month only” or “from this month on”.{" "}
        <Link className="text-primary underline" to="/transactions">
          See the transactions
        </Link>
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- from the workbook
function ExcelPicker({ year, onDone, notify }: { year: number; onDone: () => void; notify: Notify }) {
  const refresh = useRefresh();
  const rows = useQuery({ queryKey: ["recurring", "excel", year], queryFn: () => fetchExcelRows(year) });
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const chosen = picked ?? new Set((rows.data ?? []).filter((r) => r.suggested).map((r) => r.name));
  const make = useMutation({
    mutationFn: () => createFromExcel(year, [...chosen]),
    onSuccess: (r) => {
      refresh();
      notify(
        `${r.templates} templates created; ${year} filled with ${r.entries} months, ${r.linked} linked to the sheet’s lines.`,
      );
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const toggle = (name: string) => {
    const next = new Set(chosen);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setPicked(next);
  };
  return (
    <section className="mt-4 rounded-2xl bg-surface p-4 md:p-5" aria-label={`Rows of the ${year} sheet`}>
      <h2 className="font-display text-2xl font-bold">Rows of the Cash Flow {year} sheet</h2>
      {rows.isLoading && <p className="mt-2 text-muted">Loading the sheet’s rows…</p>}
      {rows.data && !rows.data.length && (
        <p className="mt-2">
          No {year} sheet is loaded.{" "}
          <Link className="text-primary underline" to="/import">
            Load the Excel history
          </Link>{" "}
          first.
        </p>
      )}
      {rows.data && rows.data.length > 0 && (
        <>
          <p className="mt-2 text-muted">
            Rows with a value in three or more months, or a planned value, are ticked. Each becomes a
            template, and {year} is filled with the sheet’s amounts.
          </p>
          <ul className="mt-3 grid gap-1 md:grid-cols-2">
            {rows.data.map((r) => (
              <li key={r.name}>
                <label className={`flex items-center gap-2 ${r.exists ? "text-muted" : ""}`}>
                  <input
                    type="checkbox"
                    className="h-5 w-5"
                    disabled={r.exists || r.category_id == null}
                    checked={!r.exists && chosen.has(r.name)}
                    onChange={() => toggle(r.name)}
                  />
                  <span>
                    {r.name}
                    <span className="text-sm text-muted">
                      {" "}
                      · {r.months} {r.months === 1 ? "month" : "months"} ·{" "}
                      <span className="num">{money(r.latest)}</span>
                      {r.exists ? " · already a template" : ""}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex gap-2">
            <button
              className="btn btn-primary"
              disabled={make.isPending || chosen.size === 0}
              onClick={() => make.mutate()}
            >
              {make.isPending ? "Creating…" : `Create ${chosen.size} templates`}
            </button>
            <button className="btn btn-quiet" onClick={onDone}>
              Cancel
            </button>
          </div>
        </>
      )}
    </section>
  );
}
