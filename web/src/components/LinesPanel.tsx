import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  createRule,
  fetchCategories,
  fetchFlowLines,
  searchLines,
  statementPageUrl,
  updateTransaction,
  type FlowFilter,
  type FlowLine,
} from "../api";
import { addMonths, money, monthLong, num } from "../money";
import CategoryPicker from "./CategoryPicker";

// The lines behind a number (ADR-048): opens over the page from any total, lists every line
// with where it came from, fixes a category in place (Always: a rule for next time), and searches
// for lines that should be in this number but aren't. Closing returns to the same spot.

export type LinesTarget = {
  title: string;
  month: string; // YYYY-MM-01
  filter: FlowFilter;
  moveTo?: number | null; // the category a found line moves into ("Move here")
};

const short = (d: string) =>
  new Date(`${d}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export default function LinesPanel({ target, onClose }: { target: LinesTarget; onClose: () => void }) {
  const qc = useQueryClient();
  const key = ["cashflow", "lines", target.month, target.filter];
  const lines = useQuery({ queryKey: key, queryFn: () => fetchFlowLines(target.month, target.filter) });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [always, setAlways] = useState(false);
  const [text, setText] = useState("");
  const [asked, setAsked] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const found = useQuery({
    queryKey: ["cashflow", "search", asked, target.month],
    queryFn: () => searchLines(asked, target.month),
    enabled: asked.length >= 2,
  });

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  const recat = useMutation({
    mutationFn: async ({ line, category_id }: { line: FlowLine; category_id: number }) => {
      await updateTransaction(line.transaction_id, { category_id });
      if (always && line.merchant_key)
        await createRule({ pattern: line.merchant_key, match_type: "contains", category_id, priority: 50 });
    },
    onSuccess: () => {
      setNote(always ? "Changed, and saved a rule for next time." : "Changed.");
      ["cashflow", "spending", "todo", "review", "transactions", "rules"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      );
    },
    onError: (e: Error) => setNote(e.message),
  });

  // ADR-089: the month a line counts in, when the rule got it wrong (a bonus isn't next month's pay).
  const move = useMutation({
    mutationFn: ({ line, month }: { line: FlowLine; month: string }) =>
      updateTransaction(line.transaction_id, { counts_in: month }),
    onSuccess: (_, { month }) => {
      setNote(`Moved: it counts in ${monthLong(month)} now.`);
      qc.invalidateQueries(); // every number by month can change
    },
    onError: (e: Error) => setNote(e.message),
  });
  const mover = (l: FlowLine) =>
    l.source === "excel_history" || !l.cash_month ? null : (
      <CountsIn l={l} onMove={(month) => move.mutate({ line: l, month })} />
    );

  const total = (lines.data ?? []).reduce((s, l) => s + num(l.amount), 0);
  const groups = cats.data ?? [];

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label={target.title}
    >
      <button aria-label="Close" className="absolute inset-0 bg-ink/30" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-2xl flex-col overflow-y-auto bg-ground shadow-xl">
        <header className="sticky top-0 z-10 border-b border-line bg-ground p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="font-display text-2xl font-bold">{target.title}</h2>
              <p className="text-sm text-muted">
                {new Date(`${target.month}T00:00:00`).toLocaleDateString("en-US", {
                  month: "long",
                  year: "numeric",
                })}
                {lines.data && (
                  <>
                    {" · "}
                    {lines.data.length} {lines.data.length === 1 ? "line" : "lines"} ·{" "}
                    <span className="num font-semibold">{money(total)}</span>
                  </>
                )}
              </p>
            </div>
            <button className="btn btn-secondary h-9 px-4 text-sm" onClick={onClose}>
              Back
            </button>
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
            When I change a category, make it a rule for that merchant too
          </label>
          {note && (
            <p role="status" className="mt-2 text-sm text-primary">
              {note}
            </p>
          )}
        </header>

        <section aria-label="Lines" className="p-5">
          {(lines.data ?? []).some((l) => l.source === "excel_history") && (
            <p className="mb-3 rounded-xl bg-surface px-4 py-3 text-sm">
              This month counts the <strong>Cash Flow workbook</strong>: its amount is one line per category,
              so there are no payments to see here. The statements count from the month chosen under “Where
              the numbers come from” on Cash flow.
            </p>
          )}
          {lines.error && <p className="text-warn">{(lines.error as Error).message}</p>}
          {!lines.data && !lines.error && <p className="text-muted">Loading the lines…</p>}
          {lines.data && !lines.data.length && <p className="text-muted">No lines.</p>}
          <ul className="divide-y divide-line">
            {(lines.data ?? []).map((l) => (
              <LineRow
                key={l.transaction_id}
                l={l}
                mover={mover(l)}
                picker={
                  l.source === "excel_history" ? null : (
                    <CategoryPicker
                      label={`Category for ${l.description}`}
                      hideLabel
                      groups={groups}
                      value={l.category_id ?? ""}
                      placeholder="No category"
                      onChange={(id) =>
                        id !== "" && id !== l.category_id && recat.mutate({ line: l, category_id: id })
                      }
                    />
                  )
                }
              />
            ))}
          </ul>
        </section>

        <section aria-label="Find a missing line" className="border-t border-line p-5">
          <h3 className="font-semibold">Missing something?</h3>
          <p className="text-sm text-muted">
            Search every line from the month before to the month after, counted here or not.
          </p>
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setAsked(text.trim());
            }}
          >
            <input
              className="field"
              placeholder="Merchant, person or words in the description"
              aria-label="Search lines"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button className="btn btn-primary" type="submit" disabled={text.trim().length < 2}>
              Search
            </button>
          </form>
          {found.data && !found.data.length && <p className="mt-3 text-sm text-muted">Nothing found.</p>}
          <ul className="mt-2 divide-y divide-line">
            {(found.data ?? []).map((l) => (
              <LineRow
                key={l.transaction_id}
                l={l}
                mover={mover(l)}
                picker={
                  target.moveTo && l.category_id !== target.moveTo ? (
                    <button
                      className="btn btn-secondary h-9 px-3 text-sm"
                      onClick={() => recat.mutate({ line: l, category_id: target.moveTo! })}
                    >
                      Move here
                    </button>
                  ) : (
                    <CategoryPicker
                      label={`Category for ${l.description}`}
                      hideLabel
                      groups={groups}
                      value={l.category_id ?? ""}
                      placeholder="No category"
                      onChange={(id) =>
                        id !== "" && id !== l.category_id && recat.mutate({ line: l, category_id: id })
                      }
                    />
                  )
                }
              />
            ))}
          </ul>
        </section>
      </aside>
    </div>
  );
}

/** Which month the line counts in: the month of its date or the one before or after it. */
function CountsIn({ l, onMove }: { l: FlowLine; onMove: (month: string) => void }) {
  const own = `${l.txn_date.slice(0, 7)}-01`;
  const now = l.cash_month ?? own;
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      Counts in
      <select
        className="field !h-8 !w-auto !py-0 text-xs"
        aria-label={`Month ${l.description} counts in`}
        value={now}
        onChange={(e) => e.target.value !== now && onMove(e.target.value)}
      >
        {[addMonths(own, -1), own, addMonths(own, 1)].map((m) => (
          <option key={m} value={m}>
            {monthLong(m)}
          </option>
        ))}
      </select>
      {l.month_override && <span>(set by hand)</span>}
    </label>
  );
}

function LineRow({ l, picker, mover }: { l: FlowLine; picker: React.ReactNode; mover?: React.ReactNode }) {
  const parts = [
    l.account_name,
    l.person,
    l.counterparty && `with ${l.counterparty}`,
    l.type !== "expense" && l.type !== "income" ? l.type.replace("_", " ") : null,
    l.source === "bank_sync" ? "synced, waiting for its statement" : null,
    l.source === "excel_history" ? "from the Cash Flow workbook" : null,
  ].filter(Boolean);
  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="flex items-baseline gap-2">
          <span className="num shrink-0 text-sm text-muted">{short(l.txn_date)}</span>
          <span className="truncate font-semibold" title={l.description}>
            {l.description}
          </span>
        </p>
        <p className="text-sm text-muted">
          {parts.join(" · ")}
          {l.category_name && <> · {l.category_name}</>}
          {l.notes && <> · “{l.notes}”</>}
          {l.statement_file_id && (
            <>
              {" · "}
              <a
                className="text-primary underline"
                target="_blank"
                rel="noreferrer"
                href={statementPageUrl(l.statement_file_id)}
              >
                statement
              </a>
            </>
          )}
        </p>
        {mover}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className={`num font-semibold ${num(l.amount) > 0 ? "text-flow-in" : ""}`}>
          {money(l.amount)}
        </span>
        {picker && <div className="w-52">{picker}</div>}
      </div>
    </li>
  );
}
