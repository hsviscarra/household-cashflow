import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  fetchAccounts,
  fetchCategories,
  fetchRecurringGrid,
  fetchTemplates,
  generateMonth,
  matchRecurring,
} from "../api";
import { monthLong, monthName, monthShort } from "../money";
import { type Notify, type Selected, isIncome, thisMonth, totals, useRefresh } from "./recurring/shared";
import { FoundBills } from "./recurring/FoundBills";
import { Block, TotalRow } from "./recurring/Grid";
import { CellPanel } from "./recurring/CellPanel";
import { TemplateForm, TemplateEditor } from "./recurring/TemplateForms";
import { CopyForm, ExcelPicker } from "./recurring/ExcelPicker";

export { TemplateForm } from "./recurring/TemplateForms";

export { billName } from "./recurring/FoundBills";

export { cellValue, EVERY, totals } from "./recurring/shared";

export default function RecurringPage({ embedded = false }: { embedded?: boolean }) {
  const [params, setParams] = useSearchParams();
  const now = thisMonth();
  const year = Number(params.get("year")) || Number(now.slice(0, 4));
  // Keeps the rest of the address (the Bills page's view, ADR-031).
  const setYear = (y: number) => {
    const next = new URLSearchParams(params);
    next.set("year", String(y));
    setParams(next);
  };
  const grid = useQuery({ queryKey: ["recurring", "grid", year], queryFn: () => fetchRecurringGrid(year) });
  useQuery({ queryKey: ["categories"], queryFn: fetchCategories }); // ready for the forms
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
      {embedded ? (
        <h2 className="font-display text-3xl font-bold leading-tight">
          {rows.length
            ? `${monthLong(`${month}-01`)}: ${matched} of ${inMonth.length} recurring items paid`
            : "Recurring"}
        </h2>
      ) : (
        <h1 className="font-display text-4xl font-bold leading-tight">
          {rows.length
            ? `${monthLong(`${month}-01`)}: ${matched} of ${inMonth.length} recurring items paid`
            : "Recurring"}
        </h1>
      )}
      <p className="mt-2 text-lg text-muted">
        Salary, rent, fees and payments that repeat each month: what you expect, and the lines that paid it.
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-3">
        <div className="flex gap-1" role="group" aria-label="Year">
          <button className="btn btn-quiet h-11 px-3" onClick={() => setYear(year - 1)}>
            ← {year - 1}
          </button>
          <span className="flex h-11 items-center px-3 font-display text-xl font-bold">{year}</span>
          <button className="btn btn-quiet h-11 px-3" onClick={() => setYear(year + 1)}>
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
              if (!e.target.value.startsWith(String(year))) setYear(Number(e.target.value.slice(0, 4)));
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

      <FoundBills notify={notify} />

      {panel === "copy" && <CopyForm month={month} onDone={() => setPanel(null)} notify={notify} />}
      {panel === "new" && (
        <TemplateForm
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
          accounts={accounts.data ?? []}
          notify={notify}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}
