import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createHolding,
  deleteHolding,
  deleteHoldingValue,
  fetchBalanceSheet,
  fetchCategories,
  fetchTemplates,
  setHoldingValue,
  updateHolding,
  type BalanceSheet,
  type HoldingClass,
  type SheetItem,
} from "../api";
import { categoryOptions } from "../categories";
import { TrendLine } from "../components/charts";
import { localToday, money, monthLong, monthShort, num } from "../money";

type Notify = (message: string, tone?: "good" | "bad") => void;

export const CLASSES: {
  id: HoldingClass;
  label: string;
  side: "asset" | "liability" | null;
  group: string;
}[] = [
  { id: "property", label: "Property", side: "asset", group: "Property" },
  { id: "vehicle", label: "Vehicle", side: "asset", group: "Vehicles" },
  { id: "investment", label: "Investment", side: "asset", group: "Investments" },
  { id: "cash", label: "Cash or savings", side: "asset", group: "Cash" },
  {
    id: "purchase",
    label: "Purchase in progress (down payment)",
    side: "asset",
    group: "Purchases in progress",
  },
  { id: "loan", label: "Loan", side: "liability", group: "Loans" },
  { id: "card", label: "Credit card", side: "liability", group: "Credit cards" },
  { id: "personal_loan", label: "Money owed to a person", side: "liability", group: "Owed to people" },
  { id: "other", label: "Other", side: null, group: "Other" },
];
const SOURCE: Record<string, string> = {
  statement: "latest statement",
  excel: "Cash Flow sheet",
  manual: "entered here",
  lines: "payments in its category",
};
const today = () => localToday();
const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

/** "Net worth 175,193.31: you own 233,006.95 and owe 57,813.64." */
export function sheetHeadline(s: BalanceSheet): string {
  if (!s.items.length) return "Debt & Net Worth";
  const net = num(s.net_worth);
  return `Net worth ${net < 0 ? "−" : ""}${money(Math.abs(net))}: you own ${money(s.assets)} and owe ${money(s.liabilities)}`;
}

function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["networth"] });
}

export default function BalanceSheetSection() {
  const q = useQuery({ queryKey: ["networth"], queryFn: fetchBalanceSheet });
  const [adding, setAdding] = useState(false);
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });
  const s = q.data;
  const active = s?.items.filter((i) => i.is_active) ?? [];
  const paused = s?.items.filter((i) => !i.is_active) ?? [];

  return (
    <section aria-label="Balance sheet">
      <h1 className="font-display text-4xl font-bold leading-tight">
        {s ? sheetHeadline(s) : "Debt & Net Worth"}
      </h1>
      <p className="mt-2 text-lg text-muted">
        What you own and owe today: property, vehicles, investments, bank balances and the new house’s down
        payment; loans, credit cards and money owed to people.
      </p>
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the balance sheet: {(q.error as Error).message}
        </p>
      )}
      {!s && !q.error && <p className="mt-6 text-muted">Adding up what you own and owe…</p>}
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
      {s && (
        <>
          <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="You own" value={money(s.assets)} />
            <Tile label="You owe" value={money(s.liabilities)} />
            <Tile
              label="Net worth"
              value={`${num(s.net_worth) < 0 ? "−" : ""}${money(Math.abs(num(s.net_worth)))}`}
            />
            <Tile label="Still to pay on purchases" value={money(s.commitments)} hint="not counted yet" />
          </dl>
          <div className="mt-4">
            <button className="btn btn-primary" onClick={() => setAdding(!adding)}>
              {adding ? "Close" : "Add something you own or owe"}
            </button>
          </div>
          {adding && <HoldingForm onDone={() => setAdding(false)} notify={notify} />}

          <Side
            title="What you own"
            items={active.filter((i) => i.side === "asset")}
            total={s.assets}
            notify={notify}
          />
          <Side
            title="What you owe"
            items={active.filter((i) => i.side === "liability")}
            total={s.liabilities}
            notify={notify}
          />
          {paused.length > 0 && <Side title="Paused (not counted)" items={paused} notify={notify} />}

          <h2 className="mt-10 font-display text-2xl font-bold">Net worth over time</h2>
          <div className="mt-3 rounded-2xl bg-surface p-4 md:p-6">
            <TrendLine
              title={`Net worth by month, ${monthLong(s.series[0].month)} to ${monthLong(s.series[s.series.length - 1].month)}`}
              data={s.series.map((p, i) => ({
                key: p.month,
                value: num(p.net),
                tick: i % 3 === 2 || i === s.series.length - 1 ? monthShort(p.month) : undefined,
                tooltip: (
                  <>
                    <strong>{monthLong(p.month)}</strong>
                    <span className="num block">Net {money(p.net)}</span>
                    <span className="num block text-muted">
                      Own {money(p.assets)} · owe {money(p.liabilities)}
                    </span>
                  </>
                ),
              }))}
            />
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-muted">The numbers</summary>
              <table className="mt-2 w-full">
                <caption className="sr-only">Assets, liabilities and net worth by month</caption>
                <thead className="text-muted">
                  <tr>
                    <th scope="col" className="py-1 text-left font-normal">
                      Month
                    </th>
                    <th scope="col" className="py-1 text-right font-normal">
                      Own
                    </th>
                    <th scope="col" className="py-1 text-right font-normal">
                      Owe
                    </th>
                    <th scope="col" className="py-1 text-right font-normal">
                      Net
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {s.series.map((p) => (
                    <tr key={p.month}>
                      <th scope="row" className="py-1 text-left font-normal">
                        {monthLong(p.month)}
                      </th>
                      <td className="num py-1 text-right">{money(p.assets)}</td>
                      <td className="num py-1 text-right">{money(p.liabilities)}</td>
                      <td className="num py-1 text-right">{money(p.net)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
            <p className="mt-2 text-sm text-muted">
              Each month counts the values known on its last day: give an item the date you bought it so past
              months include it.
            </p>
          </div>
        </>
      )}
    </section>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="num mt-1 font-display text-2xl font-bold">{value}</dd>
      {hint && <dd className="text-xs text-muted">{hint}</dd>}
    </div>
  );
}

function Side({
  title,
  items,
  total,
  notify,
}: {
  title: string;
  items: SheetItem[];
  total?: string;
  notify: Notify;
}) {
  if (!items.length) return null;
  const groups = CLASSES.map((c) => ({ c, list: items.filter((i) => i.holding_class === c.id) })).filter(
    (g) => g.list.length,
  );
  return (
    <section className="mt-10" aria-label={title}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-2xl font-bold">{title}</h2>
        {total && <span className="num font-display text-xl font-bold">{money(total)}</span>}
      </div>
      {groups.map(({ c, list }) => (
        <div key={c.id} className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
            {c.group} · <span className="num">{money(list.reduce((sum, i) => sum + num(i.value), 0))}</span>
          </h3>
          <ul className="mt-2 grid gap-3 md:grid-cols-2">
            {list.map((i) => (
              <ItemCard key={i.key} item={i} notify={notify} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function ItemCard({ item, notify }: { item: SheetItem; notify: Notify }) {
  const [mode, setMode] = useState<"value" | "edit" | "history" | null>(null);
  const p = item.purchase;
  const editable = item.holding_id != null;
  const share = p && num(p.target) > 0 ? Math.min(1, num(p.paid) / num(p.target)) : 0;
  return (
    <li
      className={`rounded-2xl border border-line p-4 ${item.is_active ? "" : "opacity-70"}`}
      aria-label={item.name}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">{item.name}</p>
          <p className="text-sm text-muted">
            {item.as_of ? `${day(item.as_of)} · ${SOURCE[item.source ?? ""] ?? item.source}` : "No value yet"}
          </p>
        </div>
        <p className="num shrink-0 font-display text-2xl font-bold">
          {item.value != null ? money(item.value) : "—"}
        </p>
      </div>
      {p && (
        <div className="mt-3">
          <div
            className="h-2 overflow-hidden rounded-full bg-surface"
            role="progressbar"
            aria-label={`${item.name}: paid`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(share * 100)}
          >
            <div className="h-2 rounded-full bg-primary" style={{ width: `${share * 100}%` }} />
          </div>
          <p className="mt-1 text-sm">
            Paid <span className="num">{money(p.paid)}</span> of{" "}
            <span className="num">{money(p.target)}</span> · <span className="num">{money(p.remaining)}</span>{" "}
            to go
            {p.installments_left != null && p.installment
              ? ` (${p.installments_left} × ${money(p.installment)})`
              : ""}
          </p>
          {p.at_delivery != null && (
            <p className="text-sm text-muted">
              Full price <span className="num">{money(p.full_price)}</span>; at delivery{" "}
              <span className="num">{money(p.at_delivery)}</span> to finance.
            </p>
          )}
        </div>
      )}
      {item.loan && item.loan.monthly_payment && (
        <p className="mt-2 text-sm">
          Paying <span className="num">{money(item.loan.monthly_payment)}</span> a month ·{" "}
          {item.loan.payments_this_year} {item.loan.payments_this_year === 1 ? "payment" : "payments"} this
          year (<span className="num">{money(item.loan.paid_this_year)}</span>)
        </p>
      )}
      {item.notes && <p className="mt-2 text-sm text-muted">{item.notes}</p>}
      {editable ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="btn btn-secondary h-9 px-3 text-sm"
            onClick={() => setMode(mode === "value" ? null : "value")}
          >
            {p ? "Update paid so far" : "Update value"}
          </button>
          <button
            className="btn btn-quiet h-9 px-3 text-sm"
            onClick={() => setMode(mode === "edit" ? null : "edit")}
          >
            Edit
          </button>
          {item.history.length > 0 && (
            <button
              className="btn btn-quiet h-9 px-3 text-sm"
              aria-expanded={mode === "history"}
              onClick={() => setMode(mode === "history" ? null : "history")}
            >
              History ({item.history.length})
            </button>
          )}
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted">Updates with each approved statement.</p>
      )}
      {mode === "value" && <ValueForm item={item} notify={notify} onDone={() => setMode(null)} />}
      {mode === "edit" && <HoldingForm item={item} notify={notify} onDone={() => setMode(null)} />}
      {mode === "history" && <History item={item} notify={notify} />}
    </li>
  );
}

function ValueForm({ item, notify, onDone }: { item: SheetItem; notify: Notify; onDone: () => void }) {
  const refresh = useRefresh();
  const [asOf, setAsOf] = useState(today());
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const save = useMutation({
    mutationFn: () => setHoldingValue(item.holding_id!, { as_of: asOf, amount, notes: notes || null }),
    onSuccess: () => {
      refresh();
      notify(`${item.name}: ${money(amount)} on ${day(asOf)}.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <form
      className="mt-3 grid gap-2 rounded-2xl bg-surface p-3 md:grid-cols-3"
      aria-label={`New value for ${item.name}`}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <label>
        <span className="label">{item.purchase ? "Paid so far" : "Value"}</span>
        <input
          className="field num"
          type="number"
          required
          min={0}
          step="0.01"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>
      <label>
        <span className="label">On</span>
        <input
          className="field"
          type="date"
          required
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
        />
      </label>
      <label>
        <span className="label">Note (optional)</span>
        <input className="field" maxLength={400} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="md:col-span-3">
        <button className="btn btn-secondary" disabled={save.isPending || !amount}>
          Save value
        </button>
      </div>
    </form>
  );
}

function History({ item, notify }: { item: SheetItem; notify: Notify }) {
  const refresh = useRefresh();
  const remove = useMutation({
    mutationFn: deleteHoldingValue,
    onSuccess: () => {
      refresh();
      notify("Value removed.");
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <ul className="mt-3 divide-y divide-line text-sm" aria-label={`History of ${item.name}`}>
      {[...item.history].reverse().map((v, i) => (
        <li key={`${v.as_of}-${i}`} className="flex items-center justify-between gap-2 py-1">
          <span>
            {day(v.as_of)} <span className="text-muted">· {SOURCE[v.source] ?? v.source}</span>
            {v.notes && <span className="block text-xs text-muted">{v.notes}</span>}
          </span>
          <span className="flex items-center gap-2">
            <span className="num">{money(v.amount)}</span>
            {v.source === "manual" && v.snapshot_id != null && (
              <button
                className="btn btn-quiet h-8 px-2 text-xs"
                aria-label={`Remove the value of ${day(v.as_of)}`}
                onClick={() => remove.mutate(v.snapshot_id!)}
              >
                Remove
              </button>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

function HoldingForm({ item, notify, onDone }: { item?: SheetItem; notify: Notify; onDone: () => void }) {
  const refresh = useRefresh();
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const templates = useQuery({ queryKey: ["recurring", "templates"], queryFn: fetchTemplates });
  const [v, setV] = useState<Record<string, string>>({
    name: item?.name ?? "",
    holding_class: item?.holding_class ?? "property",
    side: item?.side ?? "asset",
    value: "",
    as_of: today(),
    target_amount: item?.purchase?.target ?? "",
    installment: item?.purchase?.installment ?? "",
    full_price: item?.purchase?.full_price ?? "",
    category_id: item?.category_id ? String(item.category_id) : "",
    recurring_template_id: item?.recurring_template_id ? String(item.recurring_template_id) : "",
    notes: item?.notes ?? "",
  });
  const [confirm, setConfirm] = useState(false);
  const set = (k: string, val: string) => setV({ ...v, [k]: val });
  const cls = v.holding_class as HoldingClass;
  const orNull = (x: string) => (x.trim() ? x.trim() : null);
  const body = {
    name: v.name.trim(),
    holding_class: cls,
    side: cls === "other" ? (v.side as "asset" | "liability") : null,
    target_amount: cls === "purchase" ? orNull(v.target_amount) : null,
    installment: cls === "purchase" ? orNull(v.installment) : null,
    full_price: cls === "purchase" ? orNull(v.full_price) : null,
    category_id: cls === "purchase" && v.category_id ? Number(v.category_id) : null,
    recurring_template_id: cls === "loan" && v.recurring_template_id ? Number(v.recurring_template_id) : null,
    notes: orNull(v.notes),
  };
  const save = useMutation({
    mutationFn: () =>
      item
        ? updateHolding(item.holding_id!, body)
        : createHolding({ ...body, value: orNull(v.value), as_of: v.value ? v.as_of : null }),
    onSuccess: () => {
      refresh();
      notify(item ? `${body.name} saved.` : `${body.name} added.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const pause = useMutation({
    mutationFn: () => updateHolding(item!.holding_id!, { is_active: !item!.is_active }),
    onSuccess: () => {
      refresh();
      notify(item!.is_active ? `${item!.name} paused: not counted.` : `${item!.name} counted again.`);
      onDone();
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteHolding(item!.holding_id!),
    onSuccess: () => {
      refresh();
      notify(`${item!.name} removed.`);
      onDone();
    },
  });
  const options = cats.data ? categoryOptions(cats.data) : [];
  return (
    <form
      className="mt-3 grid gap-3 rounded-2xl bg-surface p-4 md:grid-cols-4"
      aria-label={item ? `Edit ${item.name}` : "Add something you own or owe"}
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
      <label className="md:col-span-2">
        <span className="label">What it is</span>
        <select
          className="field"
          value={v.holding_class}
          onChange={(e) => set("holding_class", e.target.value)}
        >
          {CLASSES.filter((c) => c.id !== "card" || item?.holding_class === "card").map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      {cls === "other" && (
        <label>
          <span className="label">You</span>
          <select className="field" value={v.side} onChange={(e) => set("side", e.target.value)}>
            <option value="asset">own it</option>
            <option value="liability">owe it</option>
          </select>
        </label>
      )}
      {!item && (
        <>
          <label>
            <span className="label">{cls === "purchase" ? "Paid so far" : "Value"}</span>
            <input
              className="field num"
              type="number"
              min={0}
              step="0.01"
              inputMode="decimal"
              value={v.value}
              onChange={(e) => set("value", e.target.value)}
            />
          </label>
          <label>
            <span className="label">Value on</span>
            <input
              className="field"
              type="date"
              value={v.as_of}
              onChange={(e) => set("as_of", e.target.value)}
            />
          </label>
          <p className="text-sm text-muted md:col-span-2 md:self-end">
            Use the date you bought it (or took the loan) so past months include it.
          </p>
        </>
      )}
      {cls === "purchase" && (
        <>
          <Money
            label="Down payment to pay"
            value={v.target_amount}
            onChange={(x) => set("target_amount", x)}
          />
          <Money label="Each installment" value={v.installment} onChange={(x) => set("installment", x)} />
          <Money label="Full price" value={v.full_price} onChange={(x) => set("full_price", x)} />
          <label>
            <span className="label">Payments’ category (optional)</span>
            <select
              className="field"
              value={v.category_id}
              onChange={(e) => set("category_id", e.target.value)}
            >
              <option value="">None</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {cls === "loan" && (
        <label className="md:col-span-2">
          <span className="label">Monthly payment (recurring item, optional)</span>
          <select
            className="field"
            value={v.recurring_template_id}
            onChange={(e) => set("recurring_template_id", e.target.value)}
          >
            <option value="">None</option>
            {(templates.data ?? []).map((t) => (
              <option key={t.template_id} value={t.template_id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="md:col-span-4">
        <span className="label">Note (optional)</span>
        <input
          className="field"
          maxLength={400}
          value={v.notes}
          onChange={(e) => set("notes", e.target.value)}
        />
      </label>
      <div className="flex flex-wrap gap-2 md:col-span-4">
        <button className="btn btn-secondary" disabled={save.isPending || !v.name.trim()}>
          {item ? "Save" : "Add"}
        </button>
        {item && (
          <>
            <button type="button" className="btn btn-quiet" onClick={() => pause.mutate()}>
              {item.is_active ? "Pause (don’t count it)" : "Count it again"}
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
                Remove {item.name} and its values
              </button>
            )}
          </>
        )}
      </div>
    </form>
  );
}

function Money({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label>
      <span className="label">{label}</span>
      <input
        className="field num"
        type="number"
        min={0}
        step="0.01"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
