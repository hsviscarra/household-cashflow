import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  fetchCategories,
  fetchReview,
  resolveMerchant,
  suggestCategories,
  type MatchType,
  type ReviewGroup,
} from "../api";
import { categoryOptions } from "../categories";
import { money, monthLong, num, showAmount } from "../money";

type Option = { id: number; label: string };
type Notify = (message: string, tone?: "good" | "bad") => void;

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** "likely 85%", "maybe 60%", "unsure 30%": the number plus a word, never color alone. */
export function confidenceLabel(confidence: string): string {
  const v = num(confidence);
  const word = v >= 0.8 ? "likely" : v >= 0.5 ? "maybe" : "unsure";
  return `${word}, ${Math.round(v * 100)}%`;
}

export default function ReviewPage() {
  const [params, setParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : null;
  const monthDay = month ? `${month}-01` : null;
  const qc = useQueryClient();
  const review = useQuery({ queryKey: ["review", month], queryFn: () => fetchReview(monthDay) });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });
  const suggest = useMutation({
    mutationFn: () => suggestCategories(monthDay),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["review"] });
      notify(
        r.asked
          ? `Claude suggested a category for ${r.suggested} of ${r.asked} merchants. Check each one before saving.`
          : "Every merchant here already has a suggestion.",
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });

  const data = review.data;
  const unsuggested = data?.groups.filter((g) => !g.suggestion).length ?? 0;

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
        {data?.suggestions_available && unsuggested > 0 && (
          <button className="btn btn-primary" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
            {suggest.isPending ? "Asking Claude…" : `Ask Claude about ${unsuggested} merchants`}
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
          {!data.suggestions_available && data.groups.length > 0 && (
            <p className="mt-3 rounded-2xl bg-info-bg px-4 py-3">
              Claude suggestions are off: they start once the server has an ANTHROPIC_API_KEY. You can still
              choose every category here.
            </p>
          )}
          {cats.data && (
            <ul className="mt-6 space-y-4" aria-label="Merchants to review">
              {data.groups.map((g) => (
                <GroupCard
                  key={g.merchant_key}
                  group={g}
                  options={categoryOptions(cats.data)}
                  notify={notify}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function GroupCard({ group, options, notify }: { group: ReviewGroup; options: Option[]; notify: Notify }) {
  const qc = useQueryClient();
  const s = group.suggestion;
  const [categoryId, setCategoryId] = useState<number | "">(s?.category_id ?? "");
  const [saveRule, setSaveRule] = useState(true);
  const [details, setDetails] = useState(false);
  const [pattern, setPattern] = useState(group.merchant_key);
  const [matchType, setMatchType] = useState<MatchType>("contains");
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const n = group.lines.length;
  const save = useMutation({
    mutationFn: resolveMerchant,
    onSuccess: (r) => {
      ["review", "transactions", "cashflow", "rules"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      const label = options.find((o) => o.id === categoryId)?.label ?? "the category";
      notify(
        `${group.merchant_key}: ${r.categorized} ${r.categorized === 1 ? "line" : "lines"} → ${label}` +
          (r.rule_id ? ". Rule saved for next time" : "") +
          (r.also_by_rule ? `; it also categorized ${r.also_by_rule} more` : "") +
          ".",
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const headingId = `merchant-${group.merchant_key.replace(/\W+/g, "-")}`;

  return (
    <li className="rounded-2xl border border-line p-4 md:p-5" aria-labelledby={headingId}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={headingId} className="font-mono text-base font-semibold">
          {group.merchant_key}
        </h2>
        <span className="text-muted">
          {n} {n === 1 ? "line" : "lines"} · <span className="num text-ink">{showAmount(group.total)}</span>
        </span>
      </div>
      <ul className="mt-2 divide-y divide-line text-sm">
        {group.lines.map((ln) => (
          <li
            key={ln.transaction_id}
            className="flex flex-wrap items-baseline justify-between gap-x-3 py-1.5"
          >
            <span>
              <span className="num">{day(ln.txn_date)}</span>
              <span className="text-muted">
                {" "}
                · {ln.account_name ?? "—"}
                {ln.person ? ` · ${ln.person}` : ""}
              </span>
              {ln.description !== group.merchant_key && (
                <span className="block font-mono text-xs text-muted">{ln.description}</span>
              )}
            </span>
            <span className="num">{showAmount(ln.amount)}</span>
          </li>
        ))}
      </ul>

      {s && (
        <p className="mt-3 rounded-2xl bg-info-bg px-4 py-2 text-sm">
          Claude suggests <strong>{s.category_path}</strong> ({confidenceLabel(s.confidence)}): {s.reason}
        </p>
      )}

      <form
        className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (categoryId === "") return;
          save.mutate({
            merchant_key: group.merchant_key,
            category_id: categoryId,
            save_rule: saveRule,
            pattern: saveRule ? pattern.trim() || group.merchant_key : null,
            match_type: matchType,
            amount_min: saveRule && amountMin.trim() ? amountMin.trim() : null,
            amount_max: saveRule && amountMax.trim() ? amountMax.trim() : null,
            from_suggestion: !!s && categoryId === s.category_id,
          });
        }}
      >
        <label>
          <span className="label">Category for {group.merchant_key}</span>
          <select
            className="field"
            required
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Choose a category</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn btn-secondary" disabled={save.isPending || categoryId === ""}>
          {save.isPending ? "Saving…" : `Categorize ${n} ${n === 1 ? "line" : "lines"}`}
        </button>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 md:col-span-2">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={saveRule}
              onChange={(e) => setSaveRule(e.target.checked)}
            />
            Use for this merchant from now on (save a rule)
          </label>
          {saveRule && (
            <button
              type="button"
              className="text-sm text-primary underline-offset-2 hover:underline"
              aria-expanded={details}
              onClick={() => setDetails(!details)}
            >
              {details ? "Hide rule details" : "Rule details"}
            </button>
          )}
        </div>
        {saveRule && details && (
          <div className="grid gap-3 rounded-2xl bg-surface p-3 md:col-span-2 md:grid-cols-4">
            <label className="md:col-span-2">
              <span className="label">Pattern</span>
              <input
                className="field font-mono"
                maxLength={200}
                value={pattern}
                onChange={(e) => setPattern(e.target.value)}
              />
            </label>
            <label>
              <span className="label">Match</span>
              <select
                className="field"
                value={matchType}
                onChange={(e) => setMatchType(e.target.value as MatchType)}
              >
                <option value="contains">contains</option>
                <option value="starts_with">starts with</option>
                <option value="regex">regex</option>
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label>
                <span className="label">From</span>
                <input
                  className="field num"
                  type="number"
                  min={0}
                  step="0.01"
                  inputMode="decimal"
                  value={amountMin}
                  onChange={(e) => setAmountMin(e.target.value)}
                />
              </label>
              <label>
                <span className="label">Up to</span>
                <input
                  className="field num"
                  type="number"
                  min={0}
                  step="0.01"
                  inputMode="decimal"
                  value={amountMax}
                  onChange={(e) => setAmountMax(e.target.value)}
                />
              </label>
            </div>
            <p className="text-sm text-muted md:col-span-4">
              An amount range tells two bills with the same description apart (amounts without their sign;
              this merchant’s lines are {group.lines.map((ln) => money(Math.abs(num(ln.amount)))).join(", ")}
              ).
            </p>
          </div>
        )}
      </form>
    </li>
  );
}
