import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { approveBatch, fetchBatch, rejectBatch, type Batch, type StgLine } from "../api";
import { money, num, showAmount } from "../money";

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const longDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

const TYPE_LABEL: Record<string, string> = {
  expense: "Spending",
  refund: "Refund",
  income: "Money in",
  transfer: "Card payment / transfer",
  fee_interest: "Fees and interest",
  savings: "Savings",
};

export default function BatchPage() {
  const { batchId } = useParams();
  const id = Number(batchId);
  const qc = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["batch", id], queryFn: () => fetchBatch(id) });
  const approve = useMutation({
    mutationFn: () => approveBatch(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["batch", id] });
      qc.invalidateQueries({ queryKey: ["statements"] });
      qc.invalidateQueries({ queryKey: ["cashflow"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
    },
  });
  const discard = useMutation({
    mutationFn: () => rejectBatch(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["batch", id] });
      qc.invalidateQueries({ queryKey: ["statements"] });
    },
  });

  if (error)
    return (
      <p className="rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
        Could not open this import: {(error as Error).message}.{" "}
        <Link to="/import" className="underline">
          Back to Import
        </Link>
      </p>
    );
  if (!data) return <p className="text-muted">Loading the import…</p>;

  const b = data;
  const account = b.statement.accounts.map((a) => a.name).join(", ");
  const actionError = (approve.error ?? discard.error) as Error | null;

  return (
    <section>
      <Link to="/import" className="text-primary underline-offset-2 hover:underline">
        ← Import
      </Link>
      <h1 className="mt-2 font-display text-4xl font-bold leading-tight">
        {account}, {longDay(b.period_start)} – {longDay(b.period_end)}
      </h1>
      <p className="mt-2 text-muted">
        {b.statement.file_name} · {b.new_lines} new lines
        {b.duplicate_lines ? ` · ${b.duplicate_lines} already loaded` : ""}
        {b.uncategorized ? ` · ${b.uncategorized} need a category` : ""}
      </p>

      <TieOut batch={b} />

      <div aria-live="polite">
        {approve.data && (
          <p className="mt-4 rounded-2xl bg-good-bg px-4 py-3 text-good-ink">
            <strong>Import approved.</strong> {approve.data.loaded} lines loaded
            {approve.data.skipped_duplicates
              ? `, ${approve.data.skipped_duplicates} skipped as already loaded`
              : ""}
            .{" "}
            <Link to={`/transactions?month=${b.period_end.slice(0, 7)}`} className="font-semibold underline">
              See the transactions
            </Link>
          </p>
        )}
        {actionError && (
          <p className="mt-4 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">{actionError.message}</p>
        )}
      </div>

      {b.status === "preview" && !approve.data && (
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            className="btn btn-primary"
            disabled={!b.tieout_ok || approve.isPending}
            onClick={() => approve.mutate()}
          >
            {approve.isPending ? "Approving…" : "Approve import"}
          </button>
          <button
            className="btn btn-danger"
            disabled={discard.isPending}
            onClick={() => {
              if (window.confirm("Discard this preview? Nothing has been loaded.")) discard.mutate();
            }}
          >
            Discard
          </button>
          {!b.tieout_ok && (
            <span className="text-danger-ink">The statement doesn’t tie out, so it can’t be loaded.</span>
          )}
        </div>
      )}
      {b.status !== "preview" && (
        <p className="mt-6 rounded-2xl bg-surface px-4 py-3">
          {b.status === "approved" ? "Loaded" : "Discarded"} by {b.decided_by}
          {b.decided_at ? ` on ${longDay(b.decided_at.slice(0, 10))}` : ""}.
        </p>
      )}

      <ByCategory batch={b} />
      <Lines lines={b.lines} />

      {b.rejects.length > 0 && (
        <div className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          <p className="font-semibold">Lines that could not be read</p>
          <ul className="mt-1 list-disc pl-5">
            {b.rejects.map((r) => (
              <li key={`${r.page}-${r.line_no}`}>
                Page {r.page}: “{r.text}” — {r.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function TieOut({ batch }: { batch: Batch }) {
  const ok = batch.tieout_ok;
  return (
    <div className={`mt-6 rounded-2xl px-4 py-4 ${ok ? "bg-good-bg" : "bg-danger-bg"}`}>
      <h2 className={`font-display text-xl font-bold ${ok ? "text-good-ink" : "text-danger-ink"}`}>
        {ok ? "Ties out to the statement" : "Does not tie out"}
      </h2>
      <ul className="mt-2 space-y-1">
        {batch.checks.map((c) => (
          <li key={c.name} className="flex items-baseline gap-2">
            <span aria-hidden className={`shrink-0 ${c.ok ? "text-good-ink" : "text-danger-ink"}`}>
              {c.ok ? "✓" : "✗"}
            </span>
            <span>
              <span className="sr-only">{c.ok ? "Passed:" : "Failed:"}</span>
              {c.name}{" "}
              <span className="num text-muted">
                {money(c.expected)}
                {!c.ok &&
                  ` on the statement, ${money(c.actual)} in the lines (difference ${money(num(c.expected) - num(c.actual))})`}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ByCategory({ batch }: { batch: Batch }) {
  if (!batch.by_category.length) return null;
  return (
    <div className="mt-8">
      <h2 className="font-display text-2xl font-bold">By category</h2>
      <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
        <table className="w-full text-sm">
          <thead className="bg-surface text-muted">
            <tr>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Category
              </th>
              <th scope="col" className="max-md:hidden px-4 py-2 text-left font-semibold">
                Kind
              </th>
              <th scope="col" className="px-4 py-2 text-right font-semibold">
                Lines
              </th>
              <th scope="col" className="px-4 py-2 text-right font-semibold">
                Amount
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {batch.by_category.map((c) => (
              <tr key={`${c.category_path}-${c.type}`}>
                <th scope="row" className="px-4 py-2 text-left font-normal">
                  {c.category_path === "Needs a category" ? (
                    <span className="pill bg-attention-bg text-attention-ink">Needs a category</span>
                  ) : (
                    c.category_path
                  )}
                </th>
                <td className="px-4 py-2 text-muted max-md:hidden">{TYPE_LABEL[c.type] ?? c.type}</td>
                <td className="num px-4 py-2 text-right">{c.lines}</td>
                <td className="num px-4 py-2 text-right">{showAmount(c.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Lines({ lines }: { lines: StgLine[] }) {
  return (
    <div className="mt-8">
      <h2 className="font-display text-2xl font-bold">Lines</h2>
      <ul
        className="mt-3 divide-y divide-line rounded-2xl border border-line md:hidden"
        aria-label="Statement lines (list)"
      >
        {lines.map((ln) => (
          <li key={ln.stg_id} className={`px-4 py-3 ${ln.is_duplicate ? "text-muted" : ""}`}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-semibold">{ln.description}</span>
              <span className="num shrink-0">{showAmount(ln.amount)}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
              <span className="num">{day(ln.txn_date)}</span>
              <span>· {ln.person}</span>
              <span>·</span>
              {ln.category_path ?? (
                <span className="pill bg-attention-bg text-attention-ink">Needs a category</span>
              )}
              {ln.is_duplicate && <span className="pill pill-muted">Already loaded</span>}
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-3 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full text-sm">
          <caption className="sr-only">Statement lines</caption>
          <thead className="bg-surface text-muted">
            <tr>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Date
              </th>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Description
              </th>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Who
              </th>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Category
              </th>
              <th scope="col" className="px-4 py-2 text-right font-semibold">
                Amount
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {lines.map((ln) => (
              <tr key={ln.stg_id} className={ln.is_duplicate ? "text-muted" : ""}>
                <td className="num px-4 py-2">{day(ln.txn_date)}</td>
                <td className="px-4 py-2">
                  {ln.description}
                  {ln.is_duplicate && <span className="pill pill-muted ml-2">Already loaded</span>}
                </td>
                <td className="px-4 py-2">
                  {ln.person}
                  {ln.cardholder && <span className="num text-muted"> #{ln.cardholder}</span>}
                </td>
                <td className="px-4 py-2">
                  {ln.category_path ?? (
                    <span className="pill bg-attention-bg text-attention-ink">Needs a category</span>
                  )}
                </td>
                <td className="num px-4 py-2 text-right">{showAmount(ln.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-sm text-muted">
        Amounts out of the household show without a sign; money back (payments, refunds) shows with +.
      </p>
    </div>
  );
}
