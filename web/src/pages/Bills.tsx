import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchAccounts, fetchBills, fetchSubscriptions, type Bill, type BillStatus } from "../api";
import KpiCard from "../components/KpiCard";
import { addMonths, localToday, money, monthLong, monthShort, num, pct } from "../money";
import RecurringPage, { EVERY, TemplateForm } from "./Recurring";
import SubscriptionsPage from "./Subscriptions";

// Bills & subscriptions (ADR-031): one page for what repeats. The month as a calendar or by
// group, price changes, the year grid (editing) and the subscriptions found in the statements.

export const VIEWS = {
  calendar: "Calendar",
  group: "By group",
  prices: "Price changes",
  grid: "Year grid",
  found: "Found in statements",
};
type View = keyof typeof VIEWS;

const STATUS: Record<BillStatus, { label: string; cls: string }> = {
  paid: { label: "Paid", cls: "bg-good-bg text-good-ink" },
  due: { label: "Due", cls: "bg-surface text-ink" },
  late: { label: "Late", cls: "bg-danger-bg text-danger-ink" },
  skipped: { label: "Skipped", cls: "bg-surface text-muted line-through" },
};
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const isIn = (b: Bill) => b.type === "income";
const size = (b: Bill) => Math.abs(num(b.paid ?? b.expected));

/** How often, in words: "Monthly · 7th", "Yearly", "Once", "Monthly · 16 left". */
export function repeats(b: Bill) {
  const every = EVERY[String(b.every_months)] ?? `Every ${b.every_months} months`;
  const parts = [every];
  if (b.due_day)
    parts.push(
      `${b.due_day}${["th", "st", "nd", "rd"][b.due_day % 10 > 3 || [11, 12, 13].includes(b.due_day) ? 0 : b.due_day % 10]}`,
    );
  if (b.payments_left !== null) parts.push(`${b.payments_left} left`);
  return parts.join(" · ");
}

/** The month's weeks, Monday first: day numbers, null outside the month. */
export function weeks(month: string): (number | null)[][] {
  const [y, m] = month.split("-").map(Number);
  const first = (new Date(y, m - 1, 1).getDay() + 6) % 7;
  const days = new Date(y, m, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(first).fill(null),
    ...Array.from({ length: days }, (_, i) => i + 1),
  ];
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
}

export default function BillsPage({ start }: { start?: View }) {
  const [params, setParams] = useSearchParams();
  const raw = params.get("month");
  const month = raw && /^\d{4}-\d{2}$/.test(raw) ? raw : localToday().slice(0, 7);
  const view: View =
    (params.get("view") as View) in VIEWS ? (params.get("view") as View) : (start ?? "calendar");
  const [adding, setAdding] = useState(false);
  const q = useQuery({ queryKey: ["recurring", "bills", month], queryFn: () => fetchBills(`${month}-01`) });
  const subs = useQuery({ queryKey: ["subscriptions"], queryFn: fetchSubscriptions });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v === null ? next.delete(k) : next.set(k, v)));
    setParams(next);
  };
  const all = q.data?.bills ?? [];
  const out = all.filter((b) => !isIn(b) && b.status !== "skipped");
  const committed = out.reduce((s, b) => s + Math.abs(num(b.expected)), 0);
  const paid = out.filter((b) => b.status === "paid").length;
  const late = out.filter((b) => b.status === "late");
  const activeSubs = (subs.data?.subscriptions ?? []).filter((s) => s.active && s.cadence !== "possible");

  return (
    <section>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto font-display text-4xl font-bold leading-tight">
          Bills &amp; subscriptions · {monthLong(`${month}-01`)}
        </h1>
        <button
          type="button"
          className="btn btn-primary"
          aria-expanded={adding}
          onClick={() => setAdding(!adding)}
        >
          Add a bill
        </button>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1" role="group" aria-label="Month">
          <button
            type="button"
            className="btn btn-quiet h-10 px-3"
            onClick={() => set({ month: addMonths(`${month}-01`, -1).slice(0, 7) })}
          >
            ← {monthShort(addMonths(`${month}-01`, -1))}
          </button>
          <button
            type="button"
            className="btn btn-quiet h-10 px-3"
            onClick={() => set({ month: addMonths(`${month}-01`, 1).slice(0, 7) })}
          >
            {monthShort(addMonths(`${month}-01`, 1))} →
          </button>
        </div>
        <div role="group" aria-label="View" className="flex flex-wrap rounded-xl bg-surface p-1 text-sm">
          {(Object.keys(VIEWS) as View[]).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              className={`h-9 rounded-lg px-3 font-semibold ${view === v ? "bg-ground text-ink shadow-sm" : "text-muted"}`}
              onClick={() => set({ view: v === "calendar" ? null : v })}
            >
              {VIEWS[v]}
            </button>
          ))}
        </div>
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
      {adding && accounts.data && (
        <section className="card mt-4" aria-label="Add a bill or subscription">
          <h2 className="font-display text-xl font-bold">Add a bill or subscription</h2>
          <p className="mt-1 text-sm text-muted">
            Any schedule: monthly, every few months, yearly or once; set a last month for installments (18
            payments from September ends in February two years on). The statement text it contains links each
            payment.
          </p>
          <TemplateForm
            accounts={accounts.data}
            month={month}
            onDone={() => setAdding(false)}
            notify={(message, tone = "good") => setStatus({ message, tone })}
          />
        </section>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard
          label="Committed this month"
          value={money(committed)}
          note={`${out.length} ${out.length === 1 ? "item" : "items"} going out`}
        />
        <KpiCard
          label="Paid so far"
          value={`${paid} of ${out.length}`}
          note="matched to statement lines"
          tone={paid === out.length && out.length ? "good" : undefined}
        />
        <KpiCard
          label="Late"
          value={String(late.length)}
          note={
            late.length
              ? late
                  .map((b) => b.name)
                  .slice(0, 3)
                  .join(", ")
              : "nothing past its day"
          }
          tone={late.length ? "bad" : undefined}
        />
        <KpiCard
          label="Subscriptions, per year"
          value={subs.data ? money(num(subs.data.monthly_cost) * 12) : "…"}
          note={
            activeSubs
              .slice(0, 4)
              .map((s) => s.merchant)
              .join(", ") || "none found yet"
          }
        />
      </dl>

      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the bills: {(q.error as Error).message}
        </p>
      )}
      {q.data && !all.length && (view === "calendar" || view === "group" || view === "prices") && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">
          Nothing repeats in {monthLong(`${month}-01`)} yet. Add a bill, or open the Year grid to create items
          from the Cash Flow sheet.
        </p>
      )}
      {q.data && all.length > 0 && view === "calendar" && <Calendar month={month} bills={all} />}
      {q.data && all.length > 0 && view === "group" && <ByGroup bills={all} month={month} />}
      {q.data && view === "prices" && <Prices bills={all} />}
      {view === "grid" && (
        <div className="mt-8">
          <RecurringPage embedded />
        </div>
      )}
      {view === "found" && (
        <div className="mt-8">
          <SubscriptionsPage embedded />
        </div>
      )}
    </section>
  );
}

function Chip({ b }: { b: Bill }) {
  const s = STATUS[b.status];
  return (
    <span
      className={`block truncate rounded-md px-1.5 py-0.5 text-xs font-medium ${isIn(b) ? "bg-info-bg text-ink" : s.cls}`}
      title={`${b.name}: ${money(size(b))}, ${isIn(b) ? "income" : s.label.toLowerCase()}`}
    >
      {isIn(b) ? "↑ " : ""}
      {b.name} <span className="num">{money(size(b))}</span>
      <span className="sr-only">, {isIn(b) ? "money in" : s.label.toLowerCase()}</span>
    </span>
  );
}

function Calendar({ month, bills }: { month: string; bills: Bill[] }) {
  const today = localToday();
  const days = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0).getDate();
  const on = (d: number) => bills.filter((b) => b.due_day !== null && Math.min(b.due_day, days) === d);
  const noDay = bills.filter((b) => b.due_day === null);
  const sorted = [...bills].sort((a, b) => (a.due_day ?? 99) - (b.due_day ?? 99));
  return (
    <section className="card mt-6" aria-label={`${monthLong(`${month}-01`)} calendar`}>
      <div className="hidden grid-cols-7 gap-1 md:grid" role="table" aria-label="Bills by day">
        <div role="row" className="contents">
          {DOW.map((d) => (
            <div
              key={d}
              role="columnheader"
              className="px-2 pb-1 text-xs font-semibold tracking-wide text-muted uppercase"
            >
              {d}
            </div>
          ))}
        </div>
        {weeks(month).map((week, i) => (
          <div role="row" className="contents" key={i}>
            {week.map((d, j) => {
              const iso = d ? `${month}-${String(d).padStart(2, "0")}` : "";
              return (
                <div
                  key={j}
                  role="cell"
                  className={`min-h-24 rounded-lg border p-1.5 ${d ? "border-line" : "border-transparent"} ${iso === today ? "ring-2 ring-primary" : ""}`}
                >
                  {d && (
                    <>
                      <span className="num text-xs text-muted">{d}</span>
                      <div className="mt-1 space-y-1">
                        {on(d).map((b) => (
                          <Chip key={b.template_id} b={b} />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <ul className="divide-y divide-line md:hidden" aria-label="Bills by day (list)">
        {sorted.map((b) => (
          <li key={b.template_id} className="flex items-center justify-between gap-3 py-2">
            <span>
              <span className="num text-sm text-muted">
                {b.due_day ? `${monthShort(`${month}-01`)} ${b.due_day}` : "No set day"}
              </span>
              <span className="block font-medium">{b.name}</span>
            </span>
            <Chip b={b} />
          </li>
        ))}
      </ul>
      {noDay.length > 0 && (
        <div className="mt-4 hidden md:block">
          <h2 className="text-sm font-semibold text-muted">No set day yet</h2>
          <div className="mt-1 flex flex-wrap gap-2">
            {noDay.map((b) => (
              <Chip key={b.template_id} b={b} />
            ))}
          </div>
          <p className="mt-1 text-xs text-muted">
            The day comes from the lines that paid it; set it on the Year grid when it hasn’t been paid yet.
          </p>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-4 text-xs text-muted">
        {(["paid", "due", "late"] as BillStatus[]).map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <span className={`rounded-md px-1.5 py-0.5 font-medium ${STATUS[s].cls}`}>{STATUS[s].label}</span>
            {s === "paid" ? "a line paid it" : s === "due" ? "expected" : "past its day, not seen"}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="rounded-md bg-info-bg px-1.5 py-0.5 font-medium text-ink">↑ In</span>money coming
          in
        </span>
      </div>
    </section>
  );
}

function ByGroup({ bills, month }: { bills: Bill[]; month: string }) {
  const groups = [...new Set(bills.map((b) => b.group || "Other"))];
  const [open, setOpen] = useState<Set<string>>(new Set(groups.slice(0, 1)));
  const sum = (bs: Bill[], f: (b: Bill) => number) => bs.reduce((s, b) => s + f(b), 0);
  return (
    <section className="card mt-6 overflow-x-auto" aria-labelledby="by-group">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="by-group" className="font-display text-xl font-bold">
          By group, with each item inside
        </h2>
        <span className="text-sm text-muted">Open a group to see its items; edit them on the Year grid.</span>
      </div>
      <table className="mt-3 w-full text-sm">
        <thead className="text-muted">
          <tr>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Item
            </th>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Paid from
            </th>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Repeats
            </th>
            <th scope="col" className="px-2 py-1 text-right font-semibold">
              {monthShort(`${month}-01`)}
            </th>
            <th scope="col" className="px-2 py-1 text-right font-semibold">
              Last 3 months avg
            </th>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {groups.map((g) => {
            const items = bills.filter((b) => (b.group || "Other") === g);
            const lateN = items.filter((b) => b.status === "late").length;
            const changed = items.filter((b) => b.price_from).length;
            const isOpen = open.has(g);
            return (
              <Fragment key={g}>
                <tr className="bg-surface font-semibold">
                  <td className="px-2 py-1.5">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      onClick={() =>
                        setOpen((o) => {
                          const n = new Set(o);
                          if (n.has(g)) n.delete(g);
                          else n.add(g);
                          return n;
                        })
                      }
                    >
                      <span aria-hidden>{isOpen ? "▾" : "▸"}</span> {g}
                    </button>
                  </td>
                  <td />
                  <td className="px-2 py-1.5 font-normal text-muted">
                    {items.length} {items.length === 1 ? "item" : "items"}
                  </td>
                  <td className="num px-2 py-1.5 text-right">{money(sum(items, size))}</td>
                  <td className="num px-2 py-1.5 text-right">
                    {money(sum(items, (b) => Math.abs(num(b.avg3))))}
                  </td>
                  <td className="px-2 py-1.5 font-normal">
                    {lateN > 0 && (
                      <span className="rounded-md bg-danger-bg px-1.5 py-0.5 text-xs text-danger-ink">
                        {lateN} late
                      </span>
                    )}{" "}
                    {changed > 0 && (
                      <span className="rounded-md bg-attention-bg px-1.5 py-0.5 text-xs text-attention-ink">
                        {changed} price {changed === 1 ? "change" : "changes"}
                      </span>
                    )}
                  </td>
                </tr>
                {isOpen &&
                  items.map((b) => (
                    <tr key={b.template_id}>
                      <td className="px-2 py-1.5 pl-6">{b.name}</td>
                      <td className="px-2 py-1.5 text-muted">{b.account_name ?? "Any account"}</td>
                      <td className="px-2 py-1.5 text-muted">{repeats(b)}</td>
                      <td className="num px-2 py-1.5 text-right">{money(size(b))}</td>
                      <td className="num px-2 py-1.5 text-right">
                        {b.avg3 ? money(Math.abs(num(b.avg3))) : "—"}
                      </td>
                      <td className="px-2 py-1.5">
                        <span
                          className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${STATUS[b.status].cls}`}
                        >
                          {STATUS[b.status].label}
                          {b.status !== "paid" && b.due_day
                            ? ` ${monthShort(`${month}-01`)} ${b.due_day}`
                            : ""}
                        </span>
                      </td>
                    </tr>
                  ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function Prices({ bills }: { bills: Bill[] }) {
  const changed = bills.filter((b) => b.price_from && b.price_changed);
  return (
    <section className="card mt-6" aria-labelledby="prices">
      <h2 id="prices" className="font-display text-xl font-bold">
        Price changes in the last six months
      </h2>
      {!changed.length && <p className="mt-2 text-muted">No item changed its amount lately.</p>}
      <ul className="mt-3 divide-y divide-line">
        {changed.map((b) => {
          const was = Math.abs(num(b.price_from));
          const now = Math.abs(num(b.expected));
          const up = now > was;
          return (
            <li key={b.template_id} className="flex flex-wrap items-baseline justify-between gap-3 py-2">
              <span>
                <strong>{b.name}</strong>
                <span className="text-muted"> · from {monthLong(b.price_changed!)}</span>
              </span>
              <span className="num">
                {money(was)} → {money(now)}{" "}
                <span className={up ? "text-danger-ink" : "text-good-ink"}>
                  ({up ? "+" : "−"}
                  {pct(Math.abs(now - was) / (was || 1))})
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
