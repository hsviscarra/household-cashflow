import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchAccounts, fetchBills, fetchSubscriptions } from "../api";
import KpiCard from "../components/KpiCard";
import { addMonths, localToday, money, monthLong, monthShort, num } from "../money";
import RecurringPage, { TemplateForm } from "./Recurring";
import SubscriptionsPage from "./Subscriptions";
import { VIEWS, type View, isIn } from "./bills/shared";
import { Calendar } from "./bills/Calendar";
import { ByGroup, Prices } from "./bills/ByGroup";
import { MonthList } from "./bills/MonthList";

export { VIEWS, repeats, weeks } from "./bills/shared";

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
