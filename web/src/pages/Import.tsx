import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { loadHistory, previewHistory, type HistoryPreview } from "../api";
import { money, monthLong } from "../money";
import { StatementsCard } from "./ImportStatements";

const TYPE_LABEL: Record<string, string> = {
  income: "Money in",
  expense: "Spending",
  savings: "Savings",
  debt_payment: "Card or loan payment",
  fee_interest: "Fees and interest",
};

export default function ImportPage() {
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">Import</h1>
      <p className="mt-2 text-lg text-muted">
        Upload this month’s statements. The Cash Flow workbook history is loaded once, below.
      </p>
      <StatementsCard />
      <HistoryCard />
    </section>
  );
}

function HistoryCard() {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const preview = useMutation({ mutationFn: previewHistory });
  const load = useMutation({
    mutationFn: loadHistory,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cashflow"] }),
  });
  const p = preview.data;
  const error = (preview.error ?? load.error) as Error | null;

  return (
    <div className="mt-8 rounded-2xl bg-surface p-4 md:p-6">
      <h2 className="font-display text-2xl font-bold">Excel history</h2>
      <p className="mt-1 text-muted">
        Every month from the “Cash Flow” sheets, from August 2019 to June 2026. July to December 2026 are kept
        as a plan. Nothing is saved until you choose Load history.
      </p>

      <form
        className="mt-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (file) {
            load.reset();
            preview.mutate(file);
          }
        }}
      >
        <label className="min-w-64 flex-1">
          <span className="label">Workbook (.xlsx)</span>
          <input
            ref={input}
            type="file"
            accept=".xlsx"
            className="field pt-2"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              preview.reset();
              load.reset();
            }}
          />
        </label>
        <button type="submit" className="btn btn-secondary" disabled={!file || preview.isPending}>
          {preview.isPending ? "Reading…" : "Preview"}
        </button>
      </form>

      <div aria-live="polite">
        {error && <p className="mt-4 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">{error.message}</p>}
        {load.data && (
          <div className="mt-4 rounded-2xl bg-good-bg px-4 py-3 text-good-ink">
            <p className="font-semibold">History loaded.</p>
            <p>
              {load.data.transactions.toLocaleString()} monthly rows, {load.data.budget_rows} plan rows and{" "}
              {load.data.snapshots} balances saved
              {load.data.replaced_transactions
                ? `, replacing ${load.data.replaced_transactions.toLocaleString()} earlier rows`
                : ""}
              .{" "}
              <Link to="/" className="font-semibold underline">
                See the Overview
              </Link>
            </p>
          </div>
        )}
      </div>

      {p && !load.data && (
        <PreviewView p={p} busy={load.isPending} onLoad={() => file && load.mutate(file)} />
      )}
    </div>
  );
}

function PreviewView({ p, busy, onLoad }: { p: HistoryPreview; busy: boolean; onLoad: () => void }) {
  const toConfirm = p.mapping.filter((m) => m.review);
  const typed = p.mismatches.filter((m) => m.typed_total);
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const blocked = p.unmapped.length > 0;

  return (
    <div className="mt-6 space-y-6">
      <p className="text-lg">
        <strong>{p.months} months</strong>, {p.first_month && monthLong(p.first_month)} to{" "}
        {p.last_month && monthLong(p.last_month)}: {p.actual_rows.toLocaleString()} rows, {p.plan_rows} plan
        rows, {p.snapshots.length} balances.
      </p>

      <div className="overflow-x-auto rounded-2xl border border-line bg-ground">
        <table className="w-full text-sm">
          <caption className="sr-only">Totals per year</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Year
              </th>
              <th scope="col" className="px-4 py-2 text-right font-semibold">
                Months
              </th>
              <th scope="col" className="px-4 py-2 text-right font-semibold">
                Money in
              </th>
              <th scope="col" className="px-4 py-2 text-right font-semibold">
                Money out
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {p.years.map((y) => (
              <tr key={y.year}>
                <th scope="row" className="px-4 py-2 text-left font-semibold">
                  {y.year}
                </th>
                <td className="num px-4 py-2 text-right">{y.months}</td>
                <td className="num px-4 py-2 text-right">{money(y.income)}</td>
                <td className="num px-4 py-2 text-right">{money(y.outflows)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {blocked && (
        <div className="rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          <p className="font-semibold">These rows have no category yet, so the history can’t load:</p>
          <ul className="mt-1 list-disc pl-5">
            {p.unmapped.map((u) => (
              <li key={`${u.sheet}${u.cell}`}>
                {u.label} ({u.sheet} {u.cell}: {money(u.value)})
              </li>
            ))}
          </ul>
        </div>
      )}

      {toConfirm.length > 0 && (
        <details className="rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink" open>
          <summary className="cursor-pointer font-semibold">
            {plural(toConfirm.length, "row")} {toConfirm.length === 1 ? "was" : "were"} mapped by best guess.
            Check them; corrections can be made after loading.
          </summary>
          <ul className="mt-2 space-y-1">
            {toConfirm.map((m) => (
              <li key={`${m.block}${m.group}${m.label}`}>
                <strong>{m.label}</strong> → {m.category} ({TYPE_LABEL[m.type] ?? m.type},{" "}
                <span className="num">{money(m.total)}</span> over {plural(m.months, "month")}). {m.review}
              </li>
            ))}
          </ul>
        </details>
      )}

      <details className="rounded-2xl border border-line bg-ground px-4 py-3">
        <summary className="cursor-pointer font-semibold">
          {plural(p.mismatches.length, "month")} where the workbook’s TOTAL differs from its rows
          {typed.length ? ` (${typed.length} with a typed-in total)` : ""}
        </summary>
        <p className="mt-2 text-sm text-muted">
          The rows are loaded as they are. These are the rows each TOTAL formula leaves out.
        </p>
        <ul className="mt-2 space-y-1 text-sm">
          {p.mismatches.map((m) => (
            <li key={m.month}>
              <strong>{monthLong(m.month)}</strong>:{" "}
              {m.typed_total
                ? `TOTAL typed in (income ${money(m.income_workbook)}, rows ${money(m.income_rows)}; expenses ${money(m.expense_workbook)}, rows ${money(m.expense_rows)})`
                : `left out ${m.left_out.join(", ")}`}
            </li>
          ))}
        </ul>
      </details>

      {p.snapshots.length > 0 && (
        <details className="rounded-2xl border border-line bg-ground px-4 py-3">
          <summary className="cursor-pointer font-semibold">
            {p.snapshots.length} balances from the 2026 side tables
          </summary>
          <ul className="mt-2 space-y-1 text-sm">
            {p.snapshots.map((s) => (
              <li key={`${s.as_of}${s.name}`}>
                {s.name}: <span className="num">{money(s.amount)}</span> (
                {s.kind === "asset" ? "asset" : "owed"}, as of {s.as_of})
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-primary" disabled={blocked || busy || p.already_loaded} onClick={onLoad}>
          {busy ? "Loading…" : "Load history"}
        </button>
        {p.already_loaded && <span className="text-muted">This exact file is already loaded.</span>}
      </div>
    </div>
  );
}
