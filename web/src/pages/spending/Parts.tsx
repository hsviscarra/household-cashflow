import { type SpendCompare, type Spending, type SpendSlice, fetchSpendLines } from "../../api";
import { money, num, monthLong, monthShort, localToday, parts } from "../../money";
import { change, type Drill, prevMonth } from "./shared";
import { Fragment, useState } from "react";
import { usePerson, personParam } from "../../prefs";
import { useQuery } from "@tanstack/react-query";
import LinesPanel from "../../components/LinesPanel";
import { Link } from "react-router-dom";

export function Swatch({ color }: { color: string | null }) {
  return (
    <span
      aria-hidden
      className="mr-2 inline-block h-3 w-3 rounded-full align-middle"
      style={{ background: color ?? "var(--color-muted)" }}
    />
  );
}

export function CompareCells({ row }: { row: SpendCompare }) {
  return (
    <>
      <td className="num px-3 py-2 text-right">{money(row.amount)}</td>
      <td className="num hidden px-3 py-2 text-right text-muted md:table-cell">
        {change(row.amount, row.prev)}
      </td>
      <td className="num hidden px-3 py-2 text-right text-muted md:table-cell">
        {change(row.amount, row.last_year)}
      </td>
    </>
  );
}

export function CategoryTable({
  s,
  open,
  setOpen,
  setDrill,
}: {
  s: Spending;
  open: number | null;
  setOpen: (id: number | null) => void;
  setDrill: (d: Drill) => void;
}) {
  const max = Math.max(1, ...s.groups.map((g) => num(g.amount)));
  return (
    <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
      <table className="w-full text-sm">
        <caption className="sr-only">Spending by category in {monthLong(s.month)}</caption>
        <thead className="bg-surface text-muted">
          <tr>
            <th scope="col" className="px-4 py-2 text-left font-semibold">
              Category
            </th>
            <th scope="col" className="px-3 py-2 text-right font-semibold">
              {monthShort(s.month)}
            </th>
            <th scope="col" className="hidden px-3 py-2 text-right font-semibold md:table-cell">
              vs {monthShort(prevMonth(s.month))}
              {s.month.slice(0, 7) === localToday().slice(0, 7) && " (whole month)"}
            </th>
            <th scope="col" className="hidden px-3 py-2 text-right font-semibold md:table-cell">
              vs {monthShort(s.month)} {parts(s.month).year - 1}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {s.groups.map((g) => {
            const isOpen = open === g.group_id;
            const share = Math.max(0, num(g.amount)) / max;
            return (
              <Fragment key={g.group_id}>
                <tr>
                  <th scope="row" className="px-4 py-2 text-left font-medium">
                    <button
                      className="flex w-full items-center text-left"
                      aria-expanded={isOpen}
                      onClick={() => setOpen(isOpen ? null : g.group_id)}
                    >
                      <span aria-hidden className="mr-1 inline-block w-3 text-muted">
                        {isOpen ? "▾" : "▸"}
                      </span>
                      <Swatch color={g.color} />
                      <span className="min-w-0 flex-1">
                        {g.name}
                        <span
                          aria-hidden
                          className="mt-1 block h-1.5 rounded-full"
                          style={{ width: `${share * 100}%`, background: g.color ?? "var(--color-muted)" }}
                        />
                      </span>
                    </button>
                  </th>
                  <CompareCells row={g} />
                </tr>
                {isOpen &&
                  g.categories.map((c) => (
                    <tr key={c.category_id}>
                      <th scope="row" className="py-1.5 pl-12 pr-4 text-left font-normal">
                        <button
                          className="text-left text-primary underline-offset-2 hover:underline"
                          onClick={() =>
                            setDrill({
                              title: `${g.name} / ${c.name}`,
                              filter: { group_id: g.group_id, category_id: c.category_id },
                              from: "category",
                            })
                          }
                        >
                          {c.name}
                        </button>
                        <span className="text-xs text-muted">
                          {" "}
                          · {c.transactions} {c.transactions === 1 ? "line" : "lines"}
                        </span>
                      </th>
                      <CompareCells row={c} />
                    </tr>
                  ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Breakdown({
  title,
  slices,
  names,
  total,
  onPick,
}: {
  title: string;
  slices: SpendSlice[];
  names: Record<string, string>;
  total: string;
  onPick: (s: SpendSlice) => void;
}) {
  const t = Math.max(1, num(total));
  return (
    <section className="rounded-2xl border border-line p-4" aria-label={title}>
      <h3 className="font-semibold">{title}</h3>
      <ul className="mt-2 space-y-2">
        {slices.map((x) => (
          <li key={x.key}>
            <button className="w-full text-left" onClick={() => onPick(x)}>
              <span className="flex justify-between gap-2">
                <span className="underline-offset-2 hover:underline">{names[x.key] ?? x.key}</span>
                <span className="num">
                  {money(x.amount)}{" "}
                  <span className="text-muted">· {Math.round((num(x.amount) / t) * 100)}%</span>
                </span>
              </span>
              <span
                aria-hidden
                className="mt-1 block h-1.5 rounded-full bg-primary"
                style={{ width: `${Math.max(0, Math.min(1, num(x.amount) / t)) * 100}%` }}
              />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Lines({
  month,
  drill,
  onClose,
}: {
  month: string;
  drill: NonNullable<Drill>;
  onClose: () => void;
}) {
  const [person] = usePerson();
  const who = personParam(person);
  const filter = who && !drill.filter.person ? { person: who, ...drill.filter } : drill.filter;
  const q = useQuery({
    queryKey: ["spending", "lines", month, filter],
    queryFn: () => fetchSpendLines(month, filter),
  });
  const total = (q.data ?? []).reduce((sum, l) => sum + num(l.amount), 0);
  const [fix, setFix] = useState(false);
  const f = drill.filter;
  const canFix = f.category_id !== undefined || f.group_id !== undefined;
  return (
    <section className="mt-6 rounded-2xl bg-surface p-4 md:p-5" aria-label={`Lines: ${drill.title}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-bold">
          {drill.title} · {monthLong(month)}
        </h2>
        <span className="flex gap-2">
          {canFix && (
            <button className="btn btn-primary h-9 px-3" onClick={() => setFix(true)}>
              Fix or find lines
            </button>
          )}
          <button className="btn btn-quiet h-9 px-3" onClick={onClose}>
            Close
          </button>
        </span>
      </div>
      {fix && (
        <LinesPanel
          target={{
            title: drill.title,
            month,
            filter: {
              ...(f.category_id !== undefined ? { category_id: f.category_id } : { group_id: f.group_id }),
              side: "out",
              ...(who ? { person: who } : {}),
            },
            moveTo: f.category_id ?? null,
          }}
          onClose={() => setFix(false)}
        />
      )}
      {!q.data && <p className="mt-2 text-muted">Loading the lines…</p>}
      {q.data && (
        <>
          <p className="mt-1 text-muted">
            {q.data.length} {q.data.length === 1 ? "line" : "lines"} ·{" "}
            <span className="num">{money(total)}</span> ·{" "}
            <Link className="text-primary underline" to={`/transactions?month=${month.slice(0, 7)}`}>
              Edit in Transactions
            </Link>
          </p>
          <ul className="mt-3 divide-y divide-line">
            {q.data.map((l) => (
              <li key={l.transaction_id} className="flex items-center justify-between gap-3 py-1.5">
                <span className="min-w-0">
                  <span className="num">
                    {new Date(`${l.txn_date}T00:00:00`).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                  <span className="text-muted">
                    {" "}
                    · {l.account_name ?? (l.source === "excel_history" ? "Cash Flow sheet" : "—")} ·{" "}
                    {l.category_name}
                    {l.person !== "Joint" ? ` · ${l.person}` : ""}
                  </span>
                  <span className="block truncate font-mono text-xs">{l.description}</span>
                </span>
                <span className="num shrink-0">
                  {num(l.amount) < 0 ? `+${money(-num(l.amount))}` : money(l.amount)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
