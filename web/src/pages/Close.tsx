import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { closeMonth, fetchClose, reopenMonth, undoAuto, type MonthClose } from "../api";
import { addMonths, localToday, money, monthLong } from "../money";

// Close the month (ADR-087): one screen with only the exceptions. What is missing, what looks
// unusual, what the app decided on its own, the invoices check, and the report; then Close.

const MONTHS_BACK = 6; // months offered in the picker
const day = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

const GO: Record<string, string> = {
  statement: "Upload it",
  import: "Review the import",
  uncategorized: "Categorize",
  transfer: "Settle",
  recurring: "See bills",
  balance: "Check it",
  note: "See it",
};

export default function ClosePage() {
  const [params, setParams] = useSearchParams();
  const last = addMonths(`${localToday().slice(0, 7)}-01`, -1).slice(0, 7);
  const month = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : last;
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["close", month], queryFn: () => fetchClose(month) });
  const done = (c: MonthClose) => {
    qc.setQueryData(["close", month], c);
    qc.invalidateQueries({ queryKey: ["report"] });
    qc.invalidateQueries({ queryKey: ["report-months"] });
  };
  const close = useMutation({ mutationFn: () => closeMonth(month), onSuccess: done });
  const reopen = useMutation({ mutationFn: () => reopenMonth(month), onSuccess: done });
  const undo = useMutation({
    mutationFn: (ruleId: number) => undoAuto(ruleId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["close", month] }),
  });
  const c = q.data;
  const label = monthLong(`${month}-01`);
  const name = label.split(" ")[0];
  const failed = q.error ?? close.error ?? reopen.error ?? undo.error;

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">Close {label}</h1>
      <p className="mt-2 text-lg text-muted">
        Only what needs a look before the month is done: what is missing, what was unusual and what the app
        decided on its own.
      </p>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <label className="text-sm" htmlFor="close-month">
          Month
        </label>
        <select
          id="close-month"
          className="field h-10 !w-56"
          value={month}
          onChange={(e) => setParams({ month: e.target.value })}
        >
          {Array.from({ length: MONTHS_BACK }, (_, i) => addMonths(`${last}-01`, -i).slice(0, 7)).map((m) => (
            <option key={m} value={m}>
              {monthLong(`${m}-01`)}
            </option>
          ))}
        </select>
      </div>
      {failed && (
        <p role="alert" className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          {(failed as Error).message}
        </p>
      )}
      {q.isLoading && <p className="mt-6 text-muted">Loading…</p>}
      {c && (
        <div className="mt-6 space-y-6">
          <Verdict c={c} name={name} />

          <Card
            title="Missing"
            count={c.missing.length}
            empty="Nothing is missing: every account is covered."
          >
            {c.missing.map((m) => (
              <li key={m.text} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <span>{m.text}</span>
                <Link className="btn btn-secondary h-9 px-4 text-sm" to={m.link}>
                  {GO[m.kind] ?? "Open"}
                </Link>
              </li>
            ))}
          </Card>

          <Card
            title="Unusual"
            count={c.unusual.length}
            empty="No group spent well above its average of the three months before."
          >
            {c.unusual.map((u) => (
              <li key={u.group} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <span>
                  <span className="font-semibold">{u.group}</span>:{" "}
                  <span className="num">{money(u.amount)}</span>, usually about{" "}
                  <span className="num">{money(u.average)}</span>
                </span>
                <Link
                  className="btn btn-secondary h-9 px-4 text-sm"
                  to={`/transactions/categories?month=${month}`}
                >
                  See its lines
                </Link>
              </li>
            ))}
          </Card>

          <Card
            title="Decided by the app"
            count={c.decided.length}
            empty="The app saved no rule on its own for this month."
          >
            {c.decided.map((d) => (
              <li key={d.rule_id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <span>
                  <span className="font-semibold">{d.pattern}</span> → {d.category_path}
                  <span className="text-sm text-muted">
                    {" "}
                    · {d.lines} line{d.lines === 1 ? "" : "s"}
                    {!d.is_active && " · undone"}
                  </span>
                </span>
                {d.is_active && (
                  <button
                    type="button"
                    className="btn btn-quiet h-9 px-3 text-sm"
                    disabled={undo.isPending}
                    onClick={() => undo.mutate(d.rule_id)}
                  >
                    Undo
                  </button>
                )}
              </li>
            ))}
          </Card>

          <section className="card p-5" aria-labelledby="close-invoices">
            <h2 id="close-invoices" className="text-lg font-semibold">
              Invoices for taxes
            </h2>
            <p className="mt-1 text-sm text-muted">
              The app has <span className="num font-semibold text-ink">{c.invoices}</span> invoice
              {c.invoices === 1 ? "" : "s"} dated in {name}. Some never reach your email: download the month's
              list in{" "}
              <a className="text-primary underline" href={c.sri_url} target="_blank" rel="noreferrer">
                SRI en línea
              </a>{" "}
              (Facturación electrónica → Comprobantes electrónicos recibidos) and upload it on{" "}
              <Link className="text-primary underline" to="/purchases">
                Purchases
              </Link>
              ; the app gets the ones it doesn't have.
            </p>
          </section>

          <section className="card flex flex-wrap items-center justify-between gap-4 p-5">
            <p className="text-sm text-muted">
              {c.has_report ? (
                <>
                  The report is written.{" "}
                  <Link className="text-primary underline" to={`/report?month=${month}`}>
                    Read the {name} report
                  </Link>
                </>
              ) : (
                "Closing writes the month's report."
              )}
            </p>
            {c.closed_at ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={reopen.isPending}
                onClick={() => reopen.mutate()}
              >
                Reopen {name}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                disabled={!c.ready || close.isPending}
                onClick={() => close.mutate()}
              >
                {close.isPending ? "Closing…" : `Close ${name}`}
              </button>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

function Verdict({ c, name }: { c: MonthClose; name: string }) {
  if (c.closed_at)
    return (
      <p className="rounded-2xl bg-good-bg px-4 py-3 text-good-ink">
        {name} was closed on {day(c.closed_at)} by {c.closed_by}.
      </p>
    );
  if (!c.ready)
    return (
      <p className="rounded-2xl bg-info-bg px-4 py-3">
        {name} can be closed from {day(c.ready_on)}, once its last statements have had time to arrive.
      </p>
    );
  const n = c.missing.length;
  return n ? (
    <p className="rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink">
      {n} thing{n === 1 ? " is" : "s are"} still missing. You can settle {n === 1 ? "it" : "them"} first, or
      close {name} as it is.
    </p>
  ) : (
    <p className="rounded-2xl bg-good-bg px-4 py-3 text-good-ink">{name} is complete and ready to close.</p>
  );
}

function Card({
  title,
  count,
  empty,
  children,
}: {
  title: string;
  count: number;
  empty: string;
  children: ReactNode;
}) {
  return (
    <section className="card p-5" aria-label={title}>
      <h2 className="text-lg font-semibold">
        {title} <span className="num text-muted">· {count}</span>
      </h2>
      {count === 0 ? (
        <p className="mt-1 text-sm text-muted">{empty}</p>
      ) : (
        <ul className="mt-2 divide-y divide-line">{children}</ul>
      )}
    </section>
  );
}
