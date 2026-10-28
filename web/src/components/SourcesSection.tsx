import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchSources, saveSources, type SourceMonth, type Sources } from "../api";
import { money, monthLong, num } from "../money";

const signedMoney = (v: string | number) =>
  `${num(v) < 0 ? "−" : num(v) > 0 ? "+" : ""}${money(Math.abs(num(v)))}`;

/** Months to offer: every month from the workbook's first to this one, newest first. */
export function monthChoices(s: Sources, today = new Date()): string[] {
  const out: string[] = [];
  const start = s.workbook_first ?? `${today.getFullYear()}-01-01`;
  let y = today.getFullYear();
  let m = today.getMonth() + 1;
  for (;;) {
    const iso = `${y}-${String(m).padStart(2, "0")}-01`;
    if (iso < start) break;
    out.push(iso);
    m -= 1;
    if (m === 0) {
      m = 12;
      y -= 1;
    }
  }
  return out;
}

/** "From January 2026 the statements count; before it, the Cash Flow workbook." */
export function sourcesLine(s: Sources): string {
  if (!s.statements_from)
    return s.workbook_last
      ? `The Cash Flow workbook counts through ${monthLong(s.workbook_last)}; statements count after it.`
      : "Statements count for every month.";
  return `From ${monthLong(s.statements_from)} the statements count; before it, the Cash Flow workbook.`;
}

export function SourcesSection() {
  const q = useQuery({ queryKey: ["sources"], queryFn: fetchSources });
  const qc = useQueryClient();
  const [choice, setChoice] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (v: string | null) => saveSources(v),
    onSuccess: (s) => {
      qc.setQueryData(["sources"], s);
      setChoice(null);
      // Every number on every page depends on it.
      qc.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "sources" });
    },
  });
  const s = q.data;
  if (q.error)
    return <p className="mt-6 text-sm text-danger-ink">Could not load where the numbers come from.</p>;
  if (!s) return null;
  const value = choice ?? s.statements_from?.slice(0, 7) ?? "";
  return (
    <section aria-label="Where the numbers come from" className="mt-6 rounded-2xl bg-surface p-4 md:p-5">
      <h2 className="font-display text-2xl font-bold">Where the numbers come from</h2>
      <p className="mt-1">{sourcesLine(s)}</p>
      <p className="mt-1 text-sm text-muted">
        Choose the first month whose bank and card statements should count. Earlier months keep the workbook;
        from that month on the workbook stays as a reference to check the statements against. Changing it
        never deletes anything.
      </p>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(value ? `${value}-01` : null);
        }}
      >
        <label htmlFor="statements-from" className="text-sm font-semibold">
          Statements count from
        </label>
        <select
          id="statements-from"
          className="field h-10"
          value={value}
          onChange={(e) => setChoice(e.target.value)}
        >
          <option value="">After the workbook ends</option>
          {monthChoices(s).map((m) => (
            <option key={m} value={m.slice(0, 7)}>
              {monthLong(m)}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="btn btn-primary h-10 px-4"
          disabled={save.isPending || value === (s.statements_from?.slice(0, 7) ?? "")}
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        {save.error && <span className="text-sm text-danger-ink">{(save.error as Error).message}</span>}
      </form>
      {s.check.length > 0 && <Check months={s.check} />}
    </section>
  );
}

function Check({ months }: { months: SourceMonth[] }) {
  return (
    <div className="mt-5">
      <h3 className="font-display text-xl font-bold">Workbook vs statements</h3>
      <p className="text-sm text-muted">
        Months both cover. A big gap usually means a statement isn’t loaded yet or a line has another
        category.
      </p>
      <ul className="mt-2 space-y-2" aria-label="Workbook vs statements">
        {months.map((m) => {
          const gap = num(m.statements_spending) - num(m.workbook_spending);
          return (
            <li key={m.month} className="rounded-2xl border border-line bg-ground">
              <details className="p-3">
                <summary className="flex cursor-pointer flex-wrap items-baseline justify-between gap-2">
                  <span className="font-semibold">{monthLong(m.month)}</span>
                  <span className="num text-sm">
                    Spending: workbook {money(m.workbook_spending)} · statements{" "}
                    {money(m.statements_spending)}{" "}
                    <span className={Math.abs(gap) >= 1 ? "font-semibold" : "text-muted"}>
                      ({signedMoney(gap)})
                    </span>
                  </span>
                </summary>
                <p className="mt-2 text-sm">
                  Income: workbook <span className="num">{money(m.workbook_income)}</span> · statements{" "}
                  <span className="num">{money(m.statements_income)}</span> ·{" "}
                  {m.statement_lines ? `${m.statement_lines} statement lines` : "no statement lines yet"}
                </p>
                <table className="mt-2 w-full text-sm">
                  <caption className="sr-only">Spending by group, {monthLong(m.month)}</caption>
                  <thead className="text-muted">
                    <tr>
                      <th scope="col" className="py-1 text-left font-semibold">
                        Group
                      </th>
                      <th scope="col" className="py-1 text-right font-semibold">
                        Workbook
                      </th>
                      <th scope="col" className="py-1 text-right font-semibold">
                        Statements
                      </th>
                      <th scope="col" className="py-1 text-right font-semibold">
                        Gap
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {m.groups.map((g) => (
                      <tr key={g.group}>
                        <th scope="row" className="py-1 text-left font-normal">
                          {g.group}
                        </th>
                        <td className="num py-1 text-right">{money(g.workbook)}</td>
                        <td className="num py-1 text-right">{money(g.statements)}</td>
                        <td className="num py-1 text-right">{signedMoney(g.difference)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
