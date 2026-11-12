import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  editEntry,
  fetchAccounts,
  fetchBills,
  fetchSubscriptions,
  stopTemplate,
  updateTemplate,
  type Bill,
  type BillStatus,
} from "../api";
import KpiCard from "../components/KpiCard";
import { addMonths, localToday, money, monthLong, monthShort, num, pct } from "../money";
import RecurringPage, { EVERY, TemplateForm } from "./Recurring";
import SubscriptionsPage from "./Subscriptions";

// Bills & subscriptions (ADR-031, ADR-052): one page for what repeats. This month as one list by
// what needs attention (late, due, paid) with price changes inline; the calendar, by group, the
// year grid (editing) and the subscriptions found in the statements are the other views.

export const VIEWS = {
  month: "This month",
  calendar: "Calendar",
  group: "By group",
  grid: "Edit (year grid)",
  found: "Subscriptions",
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
    (params.get("view") as View) in VIEWS ? (params.get("view") as View) : (start ?? "month");
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
              onClick={() => set({ view: v === "month" ? null : v })}
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
          info="committed"
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
      {q.data && !all.length && (view === "month" || view === "calendar" || view === "group") && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">
          Nothing repeats in {monthLong(`${month}-01`)} yet. Add a bill, or open the Year grid to create items
          from the Cash Flow sheet.
        </p>
      )}
      {q.data && all.length > 0 && view === "month" && (
        <>
          <MonthList bills={all} month={month} />
          {all.some((b) => b.price_from && b.price_changed) && <Prices bills={all} />}
        </>
      )}
      {q.data && all.length > 0 && view === "calendar" && <Calendar month={month} bills={all} />}
      {q.data && all.length > 0 && view === "group" && <ByGroup bills={all} month={month} />}
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

const ORDER: { status: BillStatus; title: string; hint: string }[] = [
  { status: "late", title: "Late", hint: "Past their day and not found in a statement yet." },
  { status: "due", title: "Still to pay", hint: "Coming this month." },
  { status: "paid", title: "Paid", hint: "Matched to a statement line." },
  { status: "skipped", title: "Skipped this month", hint: "" },
];

/** This month as one list, by what needs attention first (ADR-052). */
function MonthList({ bills, month }: { bills: Bill[]; month: string }) {
  const out = bills.filter((b) => !isIn(b));
  const income = bills.filter(isIn);
  const day = (b: Bill) => b.due_day ?? 99;
  return (
    <div className="mt-6 space-y-6">
      {ORDER.map(({ status, title, hint }) => {
        const rows = out.filter((b) => b.status === status).sort((a, b) => day(a) - day(b));
        if (!rows.length) return null;
        const total = rows.reduce((s, b) => s + size(b), 0);
        return (
          <section key={status} aria-label={title} className="card">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-display text-xl font-bold">
                {title} <span className="num text-muted">· {rows.length}</span>
              </h2>
              <span className="num font-semibold">{money(total)}</span>
            </div>
            {hint && <p className="text-sm text-muted">{hint}</p>}
            <ul className="mt-3 divide-y divide-line">
              {rows.map((b) => (
                <BillRow key={b.template_id} b={b} month={month} />
              ))}
            </ul>
          </section>
        );
      })}
      {income.length > 0 && (
        <section aria-label="Money coming in" className="card">
          <h2 className="font-display text-xl font-bold">Money coming in</h2>
          <ul className="mt-3 divide-y divide-line">
            {income.map((b) => (
              <BillRow key={b.template_id} b={b} month={month} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** Fix a bill where it's shown (ADR-089): its day, skip this month, or it doesn't apply any more. */
function BillFix({ b, month, onDone }: { b: Bill; month: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [day, setDay] = useState(b.due_day ? String(b.due_day) : "");
  const [sure, setSure] = useState(false);
  const done = () => {
    ["bills", "recurring", "todo", "status", "projections"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k] }),
    );
    onDone();
  };
  const saveDay = useMutation({
    mutationFn: () => updateTemplate(b.template_id, { due_day: Number(day) }),
    onSuccess: done,
  });
  const skip = useMutation({
    mutationFn: () => editEntry(b.entry_id!, { status: b.status === "skipped" ? "planned" : "skipped" }),
    onSuccess: done,
  });
  const stop = useMutation({ mutationFn: () => stopTemplate(b.template_id, `${month}-01`), onSuccess: done });
  const failed = saveDay.error ?? skip.error ?? stop.error;
  const dayOk = /^\d{1,2}$/.test(day) && Number(day) >= 1 && Number(day) <= 31;
  return (
    <div className="mt-1 flex w-full flex-wrap items-end gap-3 rounded-[10px] bg-surface p-3 text-sm">
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (dayOk) saveDay.mutate();
        }}
      >
        <label>
          <span className="label">Day it's due</span>
          <input
            className="field num !w-20"
            inputMode="numeric"
            aria-label={`Day ${b.name} is due`}
            value={day}
            onChange={(e) => setDay(e.target.value)}
          />
        </label>
        <button className="btn btn-secondary h-10 px-3" disabled={!dayOk || saveDay.isPending}>
          Save day
        </button>
      </form>
      {b.entry_id !== null && b.status !== "paid" && (
        <button
          type="button"
          className="btn btn-secondary h-10 px-3"
          disabled={skip.isPending}
          onClick={() => skip.mutate()}
        >
          {b.status === "skipped" ? "Expect it this month" : "Skip this month"}
        </button>
      )}
      {sure ? (
        <span className="flex items-center gap-2">
          Ends before {monthLong(`${month}-01`)}; what was paid stays.
          <button
            type="button"
            className="btn btn-primary h-10 px-3"
            disabled={stop.isPending}
            onClick={() => stop.mutate()}
          >
            Yes, stop it
          </button>
          <button type="button" className="btn btn-quiet h-10 px-3" onClick={() => setSure(false)}>
            Cancel
          </button>
        </span>
      ) : (
        <button type="button" className="btn btn-quiet h-10 px-3" onClick={() => setSure(true)}>
          Doesn't apply any more
        </button>
      )}
      {failed && (
        <p role="alert" className="w-full text-danger-ink">
          {(failed as Error).message}
        </p>
      )}
    </div>
  );
}

function BillRow({ b, month }: { b: Bill; month?: string }) {
  const s = STATUS[b.status];
  const was = b.price_from ? Math.abs(num(b.price_from)) : null;
  const now = Math.abs(num(b.expected));
  const [fixing, setFixing] = useState(false);
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5">
      <span className="num w-12 shrink-0 text-sm text-muted">{b.due_day ? `Day ${b.due_day}` : "—"}</span>
      <span className="min-w-48 flex-1">
        <span className="font-semibold">{b.name}</span>
        <span className="block text-sm text-muted">
          {[b.category_path, b.account_name, repeats(b)].filter(Boolean).join(" · ")}
          {was !== null && b.price_changed && (
            <span className={now > was ? " text-danger-ink" : " text-good-ink"}>
              {" "}
              · was {money(was)} until {monthShort(b.price_changed)}
            </span>
          )}
        </span>
      </span>
      {!isIn(b) && <span className={`pill ${s.cls}`}>{s.label}</span>}
      <span className="num w-28 text-right font-semibold">
        {money(size(b))}
        {b.paid !== null && num(b.paid) !== num(b.expected) && (
          <span className="block text-xs font-normal text-muted">
            expected {money(Math.abs(num(b.expected)))}
          </span>
        )}
      </span>
      {month && (
        <button
          type="button"
          className="btn btn-quiet h-8 px-2 text-sm"
          aria-expanded={fixing}
          aria-label={`Change ${b.name}`}
          onClick={() => setFixing((v) => !v)}
        >
          {fixing ? "Close" : "Change"}
        </button>
      )}
      {month && fixing && <BillFix b={b} month={month} onDone={() => setFixing(false)} />}
    </li>
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
