import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { CategoryGroup, MatchType, Resolved, ResolveInput, Review, ReviewGroup } from "../api";
import { categoryOptions } from "../categories";
import { money, num, showAmount } from "../money";
import CategoryPicker from "./CategoryPicker";

export type Notify = (message: string, tone?: "good" | "bad") => void;

// Views a categorized line can change: refreshed after every save.
const REFRESH = ["review", "transactions", "cashflow", "rules", "batch", "batch-review"];
// "Likely" in confidenceLabel: what "Accept likely suggestions" takes.
export const LIKELY = 0.8;

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** "likely 85%", "maybe 60%", "unsure 30%": the number plus a word, never color alone. */
export function confidenceLabel(confidence: string): string {
  const v = num(confidence);
  const word = v >= LIKELY ? "likely" : v >= 0.5 ? "maybe" : "unsure";
  return `${word}, ${Math.round(v * 100)}%`;
}

/** The merchants to categorize (Review, or one statement's page) with Claude's two actions:
 * ask about the merchants without a suggestion, and accept every likely one at once. */
export function MerchantQueue(props: {
  data: Review;
  groups: CategoryGroup[];
  notify: Notify;
  resolve: (body: ResolveInput) => Promise<Resolved>;
  ask: () => Promise<{ asked: number; suggested: number }>;
  accept: () => Promise<{ merchants: number; lines: number; also_by_rule: number }>;
  label?: string;
}) {
  const qc = useQueryClient();
  const { data, notify } = props;
  const unsuggested = data.groups.filter((g) => !g.suggestion).length;
  const likely = data.groups.filter((g) => g.suggestion && num(g.suggestion.confidence) >= LIKELY).length;
  const ask = useMutation({
    mutationFn: props.ask,
    onSuccess: (r) => {
      REFRESH.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      notify(
        r.asked
          ? `Claude suggested a category for ${r.suggested} of ${r.asked} merchants. Use one with a click, or choose another.`
          : "Every merchant here already has a suggestion.",
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const accept = useMutation({
    mutationFn: props.accept,
    onSuccess: (r) => {
      REFRESH.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      notify(
        r.merchants
          ? `Accepted ${r.merchants} ${r.merchants === 1 ? "suggestion" : "suggestions"}: ${r.lines} ${r.lines === 1 ? "line" : "lines"} categorized and a rule saved for each` +
              (r.also_by_rule ? `; the rules also categorized ${r.also_by_rule} more.` : ".")
          : "No likely suggestion was left to accept.",
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });

  return (
    <>
      {data.groups.length > 0 && (data.suggestions_available || likely > 0) && (
        <div className="mt-4 flex flex-wrap gap-3">
          {data.suggestions_available && unsuggested > 0 && (
            <button className="btn btn-secondary" disabled={ask.isPending} onClick={() => ask.mutate()}>
              {ask.isPending ? "Asking Claude…" : `Ask Claude about ${unsuggested} merchants`}
            </button>
          )}
          {likely > 0 && (
            <button className="btn btn-secondary" disabled={accept.isPending} onClick={() => accept.mutate()}>
              {accept.isPending
                ? "Accepting…"
                : `✓ Accept ${likely} likely ${likely === 1 ? "suggestion" : "suggestions"}`}
            </button>
          )}
        </div>
      )}
      {!data.suggestions_available && data.groups.length > 0 && (
        <p className="mt-3 rounded-2xl bg-info-bg px-4 py-3">
          Claude suggestions are off: they start once the server has an ANTHROPIC_API_KEY. You can still
          choose every category here.
        </p>
      )}
      <ul className="mt-4 space-y-4" aria-label={props.label ?? "Merchants to review"}>
        {data.groups.map((g) => (
          <MerchantCard
            key={g.merchant_key}
            group={g}
            groups={props.groups}
            notify={notify}
            resolve={props.resolve}
          />
        ))}
      </ul>
    </>
  );
}

/** One merchant's uncategorized lines, its suggestion and the form that categorizes them. */
export function MerchantCard({
  group,
  groups,
  notify,
  resolve,
}: {
  group: ReviewGroup;
  groups: CategoryGroup[];
  notify: Notify;
  resolve: (body: ResolveInput) => Promise<Resolved>;
}) {
  const qc = useQueryClient();
  const options = categoryOptions(groups);
  const s = group.suggestion;
  const [categoryId, setCategoryId] = useState<number | "">(s?.category_id ?? "");
  const [saveRule, setSaveRule] = useState(true);
  const [details, setDetails] = useState(false);
  const [pattern, setPattern] = useState(group.merchant_key);
  const [matchType, setMatchType] = useState<MatchType>("contains");
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const n = group.lines.length;
  // One merchant can mean two things (the same shop for groceries and for a gift): untick lines
  // to categorize only some; the others stay here for another category. null = every line.
  const [picked, setPicked] = useState<Set<number> | null>(null);
  const chosen = picked ? group.lines.filter((ln) => picked.has(ln.transaction_id)) : group.lines;
  const subset = chosen.length < n;
  const toggle = (id: number) => {
    const next = new Set(picked ?? group.lines.map((ln) => ln.transaction_id));
    if (next.has(id)) next.delete(id);
    else next.add(id);
    // A rule would catch every line of this merchant: off by default when only some are chosen.
    if (next.size < n && !subset) setSaveRule(false);
    setPicked(next.size === n ? null : next);
  };
  const save = useMutation({
    mutationFn: resolve,
    onSuccess: (r, body) => {
      setPicked(null); // what is left of the merchant starts all chosen again
      REFRESH.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      const label = options.find((o) => o.id === body.category_id)?.label ?? "the category";
      notify(
        `${group.merchant_key}: ${r.categorized} ${r.categorized === 1 ? "line" : "lines"} → ${label}` +
          (r.rule_id ? ". Rule saved for next time" : "") +
          (r.also_by_rule ? `; it also categorized ${r.also_by_rule} more` : "") +
          (r.waiting_by_rule ? ` and ${r.waiting_by_rule} in statements waiting for approval` : "") +
          ".",
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const submit = (id: number) =>
    save.mutate({
      merchant_key: group.merchant_key,
      category_id: id,
      transaction_ids: subset ? chosen.map((ln) => ln.transaction_id) : null,
      save_rule: saveRule,
      pattern: saveRule ? pattern.trim() || group.merchant_key : null,
      match_type: matchType,
      amount_min: saveRule && amountMin.trim() ? amountMin.trim() : null,
      amount_max: saveRule && amountMax.trim() ? amountMax.trim() : null,
      from_suggestion: !!s && id === s.category_id,
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
            <span className="flex items-baseline gap-2">
              {n > 1 && (
                <input
                  type="checkbox"
                  className="h-5 w-5 self-center"
                  aria-label={`Include ${day(ln.txn_date)}, ${showAmount(ln.amount)}`}
                  checked={!picked || picked.has(ln.transaction_id)}
                  onChange={() => toggle(ln.transaction_id)}
                />
              )}
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
            </span>
            <span className="num">{showAmount(ln.amount)}</span>
          </li>
        ))}
      </ul>
      {n > 1 && (
        <p className="mt-1 text-xs text-muted">
          {subset
            ? `${chosen.length} of ${n} chosen. The others stay here for another category. A rule would catch every line of this merchant, so it's off; to keep two categories apart, use Rule details → amounts.`
            : "Lines of this merchant belong in different categories? Untick the ones that don't go with this one."}
        </p>
      )}

      {s && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-info-bg px-4 py-2 text-sm">
          <p>
            Claude suggests <strong>{s.category_path}</strong> ({confidenceLabel(s.confidence)}): {s.reason}
          </p>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={save.isPending || chosen.length === 0}
            aria-label={`Use ${s.category_path} for ${group.merchant_key}`}
            onClick={() => submit(s.category_id)}
          >
            ✓ Use {s.category_path}
          </button>
        </div>
      )}

      <form
        className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (categoryId !== "") submit(categoryId);
        }}
      >
        <CategoryPicker
          label={`Category for ${group.merchant_key}`}
          value={categoryId}
          onChange={setCategoryId}
          groups={groups}
          required
        />
        <button
          type="submit"
          className="btn btn-secondary"
          disabled={save.isPending || categoryId === "" || chosen.length === 0}
        >
          {save.isPending
            ? "Saving…"
            : subset
              ? `Categorize ${chosen.length} of ${n} lines`
              : `Categorize ${n} ${n === 1 ? "line" : "lines"}`}
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
