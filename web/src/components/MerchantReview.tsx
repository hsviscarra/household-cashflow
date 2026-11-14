import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { type CategoryGroup, type Many, type Resolved, type ResolveInput, type Review } from "../api";
import { num } from "../money";
import CategoryPicker from "./CategoryPicker";
import { type Notify, type LineSourceFn, REFRESH, LIKELY } from "./merchant/shared";
import { MerchantCard } from "./merchant/MerchantCard";

export { MerchantCard } from "./merchant/MerchantCard";

export { LineDetails } from "./merchant/LineDetails";

export { type Notify, type LineSourceFn, LIKELY, fullDay, confidenceLabel } from "./merchant/shared";

/** The merchants to categorize (Review, or one statement's page) with Claude's two actions:
 * ask about the merchants without a suggestion, and accept every likely one at once. */
export function MerchantQueue(props: {
  data: Review;
  groups: CategoryGroup[];
  notify: Notify;
  resolve: (body: ResolveInput) => Promise<Resolved>;
  ask: () => Promise<{ asked: number; suggested: number }>;
  accept: () => Promise<{ merchants: number; lines: number; also_by_rule: number }>;
  /** Several merchants at once (ADR-029): to one category, or (null) each to its suggestion. */
  many?: (keys: string[], categoryId: number | null) => Promise<Many>;
  /** Where a line came from (ADR-034): the statement text around it and more. */
  source?: LineSourceFn;
  label?: string;
}) {
  const qc = useQueryClient();
  const { data, notify } = props;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkCategory, setBulkCategory] = useState<number | "">("");
  const [help, setHelp] = useState(false);
  const list = useRef<HTMLUListElement>(null);
  const keys = data.groups.map((g) => g.merchant_key);
  const chosen = keys.filter((k) => selected.has(k));
  const chosenWithSuggestion = data.groups.filter((g) => selected.has(g.merchant_key) && g.suggestion).length;
  const toggle = (key: string) =>
    setSelected((old) => {
      const next = new Set(old);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const bulk = useMutation({
    mutationFn: ({ ids, category }: { ids: string[]; category: number | null }) => props.many!(ids, category),
    onSuccess: (r) => {
      setSelected(new Set());
      REFRESH.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      notify(
        `${r.merchants} ${r.merchants === 1 ? "merchant" : "merchants"} done: ${r.lines} ${r.lines === 1 ? "line" : "lines"} categorized and a rule saved for each` +
          (r.also_by_rule ? `; the rules also categorized ${r.also_by_rule} more` : "") +
          (r.skipped ? `. ${r.skipped} skipped (no suggestion, or already categorized).` : "."),
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });

  // Keyboard (ADR-029): j/k or ↓/↑ move between merchants, a accepts the suggestion, c opens the
  // category, x selects, ? shows the keys. Typing in a field is left alone.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target instanceof HTMLElement ? e.target : null;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (t && (t.isContentEditable || t.closest("input, select, textarea, [role=combobox]"))) return;
      const cards = Array.from(list.current?.querySelectorAll<HTMLElement>(":scope > li") ?? []);
      if (!cards.length) return;
      const at = cards.findIndex((c) => c.contains(document.activeElement));
      const card = at >= 0 ? cards[at] : null;
      const go = (i: number) => {
        const next = cards[Math.max(0, Math.min(cards.length - 1, i))];
        next.focus();
        next.scrollIntoView?.({ block: "nearest" });
      };
      if (e.key === "j" || e.key === "ArrowDown") go(at + 1);
      else if (e.key === "k" || e.key === "ArrowUp") go(at <= 0 ? 0 : at - 1);
      else if (e.key === "a" && card) card.querySelector<HTMLButtonElement>("[data-action=accept]")?.click();
      else if (e.key === "c" && card) card.querySelector<HTMLElement>("[role=combobox], select")?.focus();
      else if (e.key === "x" && card && card.dataset.merchant) toggle(card.dataset.merchant);
      else if (e.key === "?") setHelp((h) => !h);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
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
              {ask.isPending
                ? "Asking Claude…"
                : `Ask Claude about ${unsuggested} ${unsuggested === 1 ? "merchant" : "merchants"}`}
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
      {data.groups.length > 0 && (
        <p className="mt-3 text-sm text-muted">
          <button
            type="button"
            className="font-semibold text-primary underline"
            onClick={() => setHelp(!help)}
            aria-expanded={help}
          >
            Keyboard
          </button>
          {help && (
            <span className="ml-2">
              <kbd>j</kbd>/<kbd>k</kbd> next and previous merchant · <kbd>a</kbd> accept the suggestion ·{" "}
              <kbd>c</kbd> choose a category · <kbd>x</kbd> select · <kbd>?</kbd> show or hide these keys
            </span>
          )}
        </p>
      )}
      {props.many && data.groups.length > 1 && (
        <div
          role="region"
          aria-label="Selected merchants"
          className="sticky top-2 z-10 mt-4 flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-ground p-3 shadow-sm"
        >
          <label className="flex h-11 items-center gap-2">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={chosen.length === keys.length}
              ref={(el) => {
                if (el) el.indeterminate = chosen.length > 0 && chosen.length < keys.length;
              }}
              onChange={(e) => setSelected(new Set(e.target.checked ? keys : []))}
            />
            {chosen.length ? `${chosen.length} selected` : "Select all"}
          </label>
          {chosen.length > 0 && (
            <>
              {chosenWithSuggestion > 0 && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={bulk.isPending}
                  onClick={() => bulk.mutate({ ids: chosen, category: null })}
                >
                  ✓ Accept {chosenWithSuggestion} {chosenWithSuggestion === 1 ? "suggestion" : "suggestions"}
                </button>
              )}
              <form
                className="flex flex-wrap items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (bulkCategory !== "") bulk.mutate({ ids: chosen, category: bulkCategory });
                }}
              >
                <div className="w-72">
                  <CategoryPicker
                    label="Category for the selected merchants"
                    value={bulkCategory}
                    onChange={setBulkCategory}
                    groups={props.groups}
                  />
                </div>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={bulk.isPending || bulkCategory === ""}
                >
                  {bulk.isPending ? "Saving…" : `Categorize ${chosen.length}`}
                </button>
              </form>
            </>
          )}
        </div>
      )}
      <ul ref={list} className="mt-4 space-y-4" aria-label={props.label ?? "Merchants to review"}>
        {data.groups.map((g) => (
          <MerchantCard
            key={g.merchant_key}
            group={g}
            groups={props.groups}
            notify={notify}
            resolve={props.resolve}
            source={props.source}
            selected={props.many ? selected.has(g.merchant_key) : undefined}
            onSelect={props.many ? () => toggle(g.merchant_key) : undefined}
          />
        ))}
      </ul>
    </>
  );
}
