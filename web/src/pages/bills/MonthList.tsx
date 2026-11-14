import { type Bill, updateTemplate, editEntry, stopTemplate } from "../../api";
import { isIn, ORDER, size, STATUS, repeats } from "./shared";
import { money, monthLong, num, monthShort } from "../../money";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { useState } from "react";

/** This month as one list, by what needs attention first (ADR-052). */
export function MonthList({ bills, month }: { bills: Bill[]; month: string }) {
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
export function BillFix({ b, month, onDone }: { b: Bill; month: string; onDone: () => void }) {
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

export function BillRow({ b, month }: { b: Bill; month?: string }) {
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
