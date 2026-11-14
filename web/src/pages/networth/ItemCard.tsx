import { type SheetItem, updateHolding } from "../../api";
import { type Notify, CLASSES, freshness, today, day, useRefresh, maybeDuplicate, SOURCE } from "./shared";
import { money, num } from "../../money";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ScheduleLine, WhatIf, LoanTableUpload, ValueForm, History, Payments } from "./ItemParts";
import { HoldingForm } from "./HoldingForm";

export function Side({
  title,
  items,
  all,
  total,
  notify,
  compact = false,
}: {
  title: string;
  items: SheetItem[];
  all: SheetItem[];
  total?: string;
  notify: Notify;
  compact?: boolean;
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
          {compact ? (
            <ul className="mt-1 divide-y divide-line">
              {list.map((i) => (
                <ItemLine key={i.key} item={i} />
              ))}
            </ul>
          ) : (
            <ul className="mt-2 grid gap-3">
              {list.map((i) => (
                <ItemCard key={i.key} item={i} all={all} notify={notify} />
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}

/** One item on the overview: its name, value and how old the value is. No actions. */
export function ItemLine({ item }: { item: SheetItem }) {
  const fresh = freshness(item, today());
  return (
    <li className="flex items-baseline justify-between gap-3 py-2" aria-label={item.name}>
      <span className="min-w-0">
        <span className="font-medium">{item.name}</span>
        <span className="block text-xs text-muted">
          {item.as_of ? day(item.as_of) : "No value yet"}
          {fresh.stale && item.holding_class !== "personal_loan" && (
            <span className="ml-1 text-attention-ink">· out of date</span>
          )}
        </span>
      </span>
      <span className="num shrink-0 font-semibold">{item.value != null ? money(item.value) : "—"}</span>
    </li>
  );
}

export function ItemCard({ item, all, notify }: { item: SheetItem; all: SheetItem[]; notify: Notify }) {
  const [mode, setMode] = useState<"value" | "edit" | "history" | "payments" | null>(null);
  const refresh = useRefresh();
  const fresh = freshness(item, today());
  const twin = maybeDuplicate(item, all, today());
  const pause = useMutation({
    mutationFn: () => updateHolding(item.holding_id!, { is_active: false }),
    onSuccess: () => {
      refresh();
      notify(`${item.name} paused: no longer counted.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const isLoan = item.holding_class === "loan" && item.holding_id != null;
  const schedule = item.loan?.schedule ?? null;
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
            {item.as_of ? `${day(item.as_of)} · ${SOURCE[item.source ?? ""] ?? item.source}` : "No value yet"}{" "}
            {item.is_active && item.holding_class !== "personal_loan" && (
              <span
                className={`ml-1 rounded-md px-1.5 py-0.5 text-xs font-medium ${fresh.stale ? "bg-attention-bg text-attention-ink" : "bg-good-bg text-good-ink"}`}
              >
                {fresh.stale
                  ? fresh.age === null
                    ? "no date"
                    : `out of date · ${fresh.age} days`
                  : "up to date"}
              </span>
            )}
          </p>
          {twin && (
            <p className="mt-1 text-sm text-attention-ink">
              Probably the same money as {twin}, from the workbook.{" "}
              {item.holding_id != null && (
                <button type="button" className="font-semibold underline" onClick={() => pause.mutate()}>
                  Pause it
                </button>
              )}
            </p>
          )}
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
      {schedule && <ScheduleLine schedule={schedule} />}
      {schedule && schedule.left > 0 && <WhatIf schedule={schedule} name={item.name} />}
      {item.loan && item.loan.monthly_payment && !schedule && (
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
          {schedule && (
            <button
              className="btn btn-quiet h-9 px-3 text-sm"
              aria-expanded={mode === "payments"}
              onClick={() => setMode(mode === "payments" ? null : "payments")}
            >
              Payments
            </button>
          )}
          {isLoan && <LoanTableUpload item={item} notify={notify} replacing={schedule != null} />}
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted">Updates with each approved statement.</p>
      )}
      {mode === "value" && <ValueForm item={item} notify={notify} onDone={() => setMode(null)} />}
      {mode === "edit" && <HoldingForm item={item} notify={notify} onDone={() => setMode(null)} />}
      {mode === "history" && <History item={item} notify={notify} />}
      {mode === "payments" && <Payments item={item} />}
    </li>
  );
}
