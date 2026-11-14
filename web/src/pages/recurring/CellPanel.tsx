import {
  type GridRow,
  type RecurringTemplate,
  fetchEntry,
  editEntry,
  changeTemplateAmount,
  generateMonth,
  linkLine,
  unlinkLine,
  type Txn,
} from "../../api";
import { type Notify, useRefresh, day } from "./shared";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { monthLong, money, num, monthShort, showAmount } from "../../money";

// ---------------------------------------------------------------- one cell
export function CellPanel({
  row,
  month,
  template,
  notify,
  onClose,
}: {
  row: GridRow;
  month: string;
  template: RecurringTemplate | undefined;
  notify: Notify;
  onClose: () => void;
}) {
  const refresh = useRefresh();
  const qc = useQueryClient();
  const cell = row.cells.find((c) => c.month === month)!;
  const entry = useQuery({
    queryKey: ["recurring", "entry", cell.entry_id],
    queryFn: () => fetchEntry(cell.entry_id!),
    enabled: cell.entry_id != null,
  });
  const e = entry.data;
  const [amount, setAmount] = useState("");
  const [from, setFrom] = useState("");
  const done = (message: string) => {
    refresh();
    qc.invalidateQueries({ queryKey: ["recurring", "entry", cell.entry_id] });
    notify(message);
  };
  const fail = (err: Error) => notify(err.message, "bad");
  const edit = useMutation({
    mutationFn: (b: Parameters<typeof editEntry>[1]) => editEntry(cell.entry_id!, b),
    onSuccess: (r) =>
      done(
        r.status === "skipped"
          ? `${row.name} skipped in ${monthLong(month)}.`
          : `${row.name}, ${monthLong(month)}: ${money(Math.abs(num(r.amount)))} expected.`,
      ),
    onError: fail,
  });
  const change = useMutation({
    mutationFn: () => changeTemplateAmount(row.template_id, month, from),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recurring", "templates"] });
      done(`${row.name}: ${money(from)} from ${monthLong(month)} on.`);
    },
    onError: fail,
  });
  const gen = useMutation({
    mutationFn: () => generateMonth(month),
    onSuccess: () => done(`${monthLong(month)} generated.`),
    onError: fail,
  });
  const link = useMutation({
    mutationFn: (id: number) => linkLine(cell.entry_id!, id),
    onSuccess: () => done("Line linked."),
    onError: fail,
  });
  const unlink = useMutation({
    mutationFn: unlinkLine,
    onSuccess: () => done("Line unlinked."),
    onError: fail,
  });

  return (
    <section
      className="mt-6 rounded-2xl bg-surface p-4 md:p-5"
      aria-label={`${row.name} in ${monthLong(month)}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-bold">
          {row.name} · {monthLong(month)}
        </h2>
        <button className="btn btn-quiet h-9 px-3" onClick={onClose}>
          Close
        </button>
      </div>
      {cell.entry_id == null ? (
        <div className="mt-3">
          <p>
            Not generated yet
            {cell.expected ? `: the template expects ${money(Math.abs(num(cell.expected)))}` : ""}.
          </p>
          <button className="btn btn-secondary mt-3" disabled={gen.isPending} onClick={() => gen.mutate()}>
            Generate {monthLong(month)}
          </button>
        </div>
      ) : !e ? (
        <p className="mt-3 text-muted">Loading…</p>
      ) : (
        <div className="mt-3 grid gap-5 md:grid-cols-2">
          <div className="space-y-4">
            <p>
              Expected <strong className="num">{money(Math.abs(num(e.amount)))}</strong>
              {e.is_override && e.template_amount != null && (
                <> (this month only; the template says {money(Math.abs(num(e.template_amount)))})</>
              )}
              {e.status === "skipped" && <> · skipped</>}. Lines within{" "}
              <span className="num">{money(e.tolerance)}</span> of it are linked.
            </p>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(ev) => {
                ev.preventDefault();
                if (amount) edit.mutate({ amount });
              }}
            >
              <label>
                <span className="label">This month only</span>
                <input
                  className="field num w-36"
                  type="number"
                  min={0.01}
                  step="0.01"
                  inputMode="decimal"
                  value={amount}
                  onChange={(ev) => setAmount(ev.target.value)}
                />
              </label>
              <button className="btn btn-secondary" disabled={!amount || edit.isPending}>
                Save {monthShort(month)}
              </button>
            </form>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(ev) => {
                ev.preventDefault();
                if (from) change.mutate();
              }}
            >
              <label>
                <span className="label">From {monthLong(month)} on</span>
                <input
                  className="field num w-36"
                  type="number"
                  min={0.01}
                  step="0.01"
                  inputMode="decimal"
                  value={from}
                  onChange={(ev) => setFrom(ev.target.value)}
                />
              </label>
              <button className="btn btn-secondary" disabled={!from || change.isPending}>
                Change from {monthShort(month)} on
              </button>
            </form>
            <div className="flex flex-wrap gap-2">
              {e.is_override && (
                <button className="btn btn-quiet" onClick={() => edit.mutate({ reset: true })}>
                  Back to the template amount
                </button>
              )}
              {e.status === "planned" ? (
                <button className="btn btn-quiet" onClick={() => edit.mutate({ status: "skipped" })}>
                  Skip {monthShort(month)} (doesn’t happen)
                </button>
              ) : (
                <button className="btn btn-quiet" onClick={() => edit.mutate({ status: "planned" })}>
                  Expect it again
                </button>
              )}
            </div>
            {template && !template.match_pattern && !template.account_id && (
              <p className="text-sm text-muted">
                Tip: an account or a description pattern on the template makes matching surer when several
                items share a category (the card payments, for example).
              </p>
            )}
          </div>
          <div>
            <h3 className="font-semibold">Lines that paid it</h3>
            {e.lines.length ? (
              <LineList lines={e.lines} action="Unlink" onAction={(id) => unlink.mutate(id)} />
            ) : (
              <p className="mt-1 text-muted">None yet.</p>
            )}
            {e.candidates.length > 0 && (
              <>
                <h3 className="mt-4 font-semibold">Other lines this month</h3>
                <LineList lines={e.candidates.slice(0, 8)} action="Link" onAction={(id) => link.mutate(id)} />
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export function LineList({
  lines,
  action,
  onAction,
}: {
  lines: Txn[];
  action: string;
  onAction: (id: number) => void;
}) {
  return (
    <ul className="mt-1 divide-y divide-line">
      {lines.map((ln) => (
        <li key={ln.transaction_id} className="flex items-center justify-between gap-2 py-1.5">
          <span className="min-w-0 flex-1">
            <span className="num">{day(ln.txn_date)}</span>
            <span className="text-muted">
              {" "}
              · {ln.account_name ?? (ln.source === "excel_history" ? "Cash Flow sheet" : "—")}
            </span>
            <span className="block truncate font-mono text-xs">{ln.description}</span>
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <span className="num">{showAmount(ln.amount)}</span>
            <button
              className="btn btn-quiet h-9 px-3 text-sm"
              aria-label={`${action} ${ln.description} on ${day(ln.txn_date)}`}
              onClick={() => onAction(ln.transaction_id)}
            >
              {action}
            </button>
          </span>
        </li>
      ))}
    </ul>
  );
}
