import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  acceptSuggestions,
  fetchAuto,
  fetchCategories,
  fetchPeople,
  fetchReview,
  fetchUnmatchedTransfers,
  fetchWho,
  matchTransfers,
  resolveMany,
  resolveMerchant,
  setWho,
  suggestCategories,
  undoAuto,
} from "../api";
import { MerchantQueue, type Notify } from "../components/MerchantReview";
import { monthLong, pct, num, showAmount } from "../money";

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
      <h1 className="font-display text-4xl font-bold leading-tight">Inbox</h1>
      <p className="mt-2 text-lg text-muted">
        Lines no rule could categorize, grouped by merchant. Choose a category once; saving a rule categorizes
        this merchant from now on. Select several to do them together.
      </p>
      <AutoPanel notify={(m, t) => setStatus({ message: m, tone: t ?? "good" })} />

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
              many={resolveMany}
            />
          )}
        </>
      )}

      <Who month={month} monthDay={monthDay} notify={notify} />
      <UnmatchedTransfers month={month} monthDay={monthDay} notify={notify} />
    </section>
  );
}

const REFRESH = ["review", "transactions", "cashflow", "rules", "people", "spending"];

/** Autopilot (ADR-029): whether Claude's sure suggestions are accepted on their own, and the
 * rules it saved lately, each with Undo. */
function AutoPanel({ notify }: { notify: Notify }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["review", "auto"], queryFn: fetchAuto });
  const undo = useMutation({
    mutationFn: undoAuto,
    onSuccess: (r) => {
      REFRESH.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      notify(`Rule turned off; ${r.lines} ${r.lines === 1 ? "line is" : "lines are"} back in the Inbox.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const a = q.data;
  if (!a) return null;
  const at = pct(num(a.threshold));
  return (
    <section className="mt-4 rounded-2xl bg-surface px-4 py-3" aria-labelledby="auto-heading">
      <h2 id="auto-heading" className="font-semibold">
        {a.on
          ? `Autopilot is on: Claude’s suggestions at ${at} or more are accepted with a rule when a statement is approved.`
          : "Autopilot is off: every suggestion waits here for you."}
      </h2>
      {!a.on && (
        <p className="text-sm text-muted">
          It turns on when the server has an ANTHROPIC_API_KEY and AUTO_ACCEPT_CONFIDENCE is above 0.
        </p>
      )}
      {a.rules.length > 0 && (
        <>
          <p className="mt-2 text-sm text-muted">
            Accepted on their own in the last 30 days. Wrong one? Undo puts its lines back here.
          </p>
          <ul className="mt-1 divide-y divide-line text-sm" aria-label="Accepted on their own">
            {a.rules.map((r) => (
              <li key={r.rule_id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                <span>
                  <span className="font-mono">{r.pattern}</span> → <strong>{r.category_path}</strong>
                  <span className="text-muted">
                    {" "}
                    · {r.lines} {r.lines === 1 ? "line" : "lines"} · {day(r.accepted_at.slice(0, 10))}
                  </span>
                </span>
                <button
                  type="button"
                  className="btn btn-quiet h-9 px-3"
                  disabled={undo.isPending}
                  aria-label={`Undo ${r.pattern} → ${r.category_path}`}
                  onClick={() => undo.mutate(r.rule_id)}
                >
                  Undo
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** Transfers that say only "TRANSFERENCIA" or "ZELLE": who was it for? (ADR-029) */
function Who({ month, monthDay, notify }: { month: string | null; monthDay: string | null; notify: Notify }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["review", "who", month], queryFn: () => fetchWho(monthDay) });
  const people = useQuery({ queryKey: ["people"], queryFn: fetchPeople });
  const save = useMutation({
    mutationFn: ({ id, person }: { id: number; person: number }) => setWho(id, person),
    onSuccess: (_, v) => {
      REFRESH.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      const name = people.data?.find((p) => p.counterparty_id === v.person)?.name ?? "them";
      notify(`Marked as ${name}’s.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const rows = q.data ?? [];
  if (!rows.length) return null;
  const active = (people.data ?? []).filter((p) => p.is_active);
  return (
    <section className="mt-10" aria-labelledby="who-heading">
      <h2 id="who-heading" className="font-display text-2xl font-bold">
        Who was it for?
      </h2>
      <p className="mt-2 text-muted">
        Transfers whose description doesn’t say who{month ? "" : " (last 90 days)"}. Pick the person and the
        line gets them, and their category unless you chose one.{" "}
        <Link to="/people" className="text-primary underline">
          Add a person or a text to recognize them
        </Link>
        .
      </p>
      <ul
        className="mt-4 divide-y divide-line rounded-2xl border border-line"
        aria-label="Transfers without a person"
      >
        {rows.map((t) => (
          <li key={t.transaction_id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2">
            <span>
              <span className="num">{day(t.txn_date)}</span>
              <span className="text-muted"> · {t.account_name ?? "—"}</span>
              <span className="block font-mono text-xs text-muted">{t.description}</span>
              {t.notes && <span className="block text-xs">{t.notes}</span>}
            </span>
            <span className="flex items-center gap-3">
              <span className="num">{showAmount(t.amount)}</span>
              <label className="sr-only" htmlFor={`who-${t.transaction_id}`}>
                Who was {day(t.txn_date)} {showAmount(t.amount)} for?
              </label>
              <select
                id={`who-${t.transaction_id}`}
                className="field h-10 w-44"
                value=""
                disabled={save.isPending || !active.length}
                onChange={(e) =>
                  e.target.value && save.mutate({ id: t.transaction_id, person: Number(e.target.value) })
                }
              >
                <option value="">{active.length ? "Who?" : "No people yet"}</option>
                {active.map((p) => (
                  <option key={p.counterparty_id} value={p.counterparty_id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </span>
          </li>
        ))}
      </ul>
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
