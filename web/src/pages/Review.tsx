import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  acceptSuggestions,
  fetchCategories,
  fetchReview,
  fetchUnmatchedTransfers,
  matchTransfers,
  resolveMerchant,
  suggestCategories,
} from "../api";
import { MerchantQueue, type Notify } from "../components/MerchantReview";
import { monthLong, showAmount } from "../money";

export { confidenceLabel } from "../components/MerchantReview";

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export default function ReviewPage() {
  const [params, setParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : null;
  const monthDay = month ? `${month}-01` : null;
  const review = useQuery({ queryKey: ["review", month], queryFn: () => fetchReview(monthDay) });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });
  const data = review.data;

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">Review</h1>
      <p className="mt-2 text-lg text-muted">
        Lines no rule could categorize, grouped by merchant. Choose a category once; saving a rule categorizes
        this merchant from now on.
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-4">
        <label>
          <span className="label">Month</span>
          <input
            type="month"
            className="field w-48"
            value={month ?? ""}
            onChange={(e) => setParams(e.target.value ? { month: e.target.value } : {})}
          />
        </label>
        {month && (
          <button className="btn btn-quiet" onClick={() => setParams({})}>
            All months
          </button>
        )}
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

      {(review.error || cats.error) && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the review: {((review.error ?? cats.error) as Error).message}
        </p>
      )}
      {!data && !review.error && <p className="mt-6 text-muted">Loading the lines to review…</p>}

      {data && (
        <>
          <p className="mt-6 font-display text-2xl font-bold">
            {data.groups.length
              ? `${data.uncategorized_lines} ${data.uncategorized_lines === 1 ? "line" : "lines"} from ${data.groups.length} ${data.groups.length === 1 ? "merchant" : "merchants"} need a category${month ? ` in ${monthLong(`${month}-01`)}` : ""}.`
              : `Every line has a category${month ? ` in ${monthLong(`${month}-01`)}` : ""}.`}
          </p>
          {!data.groups.length && (
            <p className="mt-2">
              <Link
                to={month ? `/transactions?month=${month}` : "/transactions"}
                className="text-primary underline"
              >
                See the transactions
              </Link>
            </p>
          )}
          {cats.data && (
            <MerchantQueue
              data={data}
              groups={cats.data}
              notify={notify}
              resolve={resolveMerchant}
              ask={() => suggestCategories(monthDay)}
              accept={() => acceptSuggestions(monthDay)}
            />
          )}
        </>
      )}

      <UnmatchedTransfers month={month} monthDay={monthDay} notify={notify} />
    </section>
  );
}

/** Transfers whose other side is not loaded: usually the other account's statement is missing. */
function UnmatchedTransfers({
  month,
  monthDay,
  notify,
}: {
  month: string | null;
  monthDay: string | null;
  notify: Notify;
}) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["transfers", "unmatched", month],
    queryFn: () => fetchUnmatchedTransfers(monthDay),
  });
  const again = useMutation({
    mutationFn: matchTransfers,
    onSuccess: (r) => {
      ["transfers", "transactions", "cashflow", "review"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      );
      notify(
        r.pairs
          ? `Matched ${r.pairs} ${r.pairs === 1 ? "transfer" : "transfers"} with their other side.`
          : "No new pairs: the other side of these transfers is not loaded yet.",
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const rows = q.data ?? [];
  if (!rows.length) return null;
  return (
    <section className="mt-10" aria-labelledby="unmatched-heading">
      <h2 id="unmatched-heading" className="font-display text-2xl font-bold">
        Transfers without their other side
      </h2>
      <p className="mt-2 text-muted">
        These lines are transfers or card payments, but the matching line on the other account is not loaded.
        Upload that account’s statement for the same dates, or change the category if it is not a transfer.
      </p>
      <ul
        className="mt-4 divide-y divide-line rounded-2xl border border-line"
        aria-label="Unmatched transfers"
      >
        {rows.map((t) => (
          <li
            key={t.transaction_id}
            className="flex flex-wrap items-baseline justify-between gap-x-3 px-4 py-2"
          >
            <span>
              <span className="num">{day(t.txn_date)}</span>
              <span className="text-muted"> · {t.account_name ?? "—"}</span>
              <span className="block font-mono text-xs text-muted">{t.description}</span>
            </span>
            <span className="num">{showAmount(t.amount)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-3">
        <button className="btn btn-secondary" disabled={again.isPending} onClick={() => again.mutate()}>
          {again.isPending ? "Matching…" : "Match transfers again"}
        </button>
        <Link to="/import" className="btn btn-quiet">
          Upload a statement
        </Link>
      </div>
    </section>
  );
}
