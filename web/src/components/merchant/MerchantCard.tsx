import {
  type ReviewGroup,
  type CategoryGroup,
  type ResolveInput,
  type Resolved,
  type MatchType,
} from "../../api";
import { type Notify, type LineSourceFn, REFRESH, day, confidenceLabel } from "./shared";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { categoryOptions } from "../../categories";
import { useState } from "react";
import { showAmount, money, num } from "../../money";
import { LineRow } from "./LineDetails";
import CategoryPicker from "../CategoryPicker";

/** One merchant's uncategorized lines, its suggestion and the form that categorizes them. */
export function MerchantCard({
  group,
  groups,
  notify,
  resolve,
  source,
  selected,
  onSelect,
}: {
  group: ReviewGroup;
  groups: CategoryGroup[];
  notify: Notify;
  resolve: (body: ResolveInput) => Promise<Resolved>;
  source?: LineSourceFn;
  selected?: boolean;
  onSelect?: () => void;
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
    <li
      className={`rounded-2xl border p-4 outline-none focus-visible:ring-3 focus-visible:ring-primary md:p-5 ${selected ? "border-primary bg-info-bg/40" : "border-line"}`}
      aria-labelledby={headingId}
      tabIndex={-1}
      data-merchant={group.merchant_key}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex items-center gap-3">
          {onSelect && (
            <input
              type="checkbox"
              className="h-5 w-5"
              aria-label={`Select ${group.merchant_key}`}
              checked={!!selected}
              onChange={onSelect}
            />
          )}
          <h2 id={headingId} className="font-mono text-base font-semibold">
            {group.merchant_key}
          </h2>
        </span>
        <span className="text-muted">
          {n} {n === 1 ? "line" : "lines"} · <span className="num text-ink">{showAmount(group.total)}</span>
        </span>
      </div>
      <ul className="mt-2 divide-y divide-line text-sm">
        {group.lines.map((ln) => (
          <LineRow
            key={ln.transaction_id}
            ln={ln}
            merchant={group.merchant_key}
            source={source}
            check={
              n > 1 ? (
                <input
                  type="checkbox"
                  className="h-5 w-5 self-center"
                  aria-label={`Include ${day(ln.txn_date)}, ${showAmount(ln.amount)}`}
                  checked={!picked || picked.has(ln.transaction_id)}
                  onChange={() => toggle(ln.transaction_id)}
                />
              ) : null
            }
          />
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
            data-action="accept"
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
