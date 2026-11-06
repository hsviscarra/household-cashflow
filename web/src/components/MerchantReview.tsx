import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import {
  statementPageUrl,
  type CategoryGroup,
  type LineSource,
  type Many,
  type MatchType,
  type Resolved,
  type ResolveInput,
  type Review,
  type ReviewGroup,
  type ReviewLine,
} from "../api";
import { categoryOptions } from "../categories";
import { money, num, showAmount } from "../money";
import CategoryPicker from "./CategoryPicker";

export type Notify = (message: string, tone?: "good" | "bad") => void;
/** Reads where a line came from; `scope` keeps loaded and staged lines apart in the cache. */
export type LineSourceFn = { scope: string; fetch: (id: number) => Promise<LineSource> };

// Views a categorized line can change: refreshed after every save.
const REFRESH = ["review", "transactions", "cashflow", "rules", "batch", "batch-review"];
// "Likely" in confidenceLabel: what "Accept likely suggestions" takes.
export const LIKELY = 0.8;

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
/** "Tue, Oct 14, 2026": the full date, so a line can be found on the statement (ADR-034). */
export const fullDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

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

/** One line of a merchant: the full date, the account, a link to the statement page and, on
 * request, everything the statement says about it (ADR-034). */
function LineRow({
  ln,
  merchant,
  source,
  check,
}: {
  ln: ReviewLine;
  merchant: string;
  source?: LineSourceFn;
  check: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const posted = ln.post_date && ln.post_date !== ln.txn_date ? ln.post_date : null;
  return (
    <li className="py-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="flex items-baseline gap-2">
          {check}
          <span>
            <span className="num font-medium">{fullDay(ln.txn_date)}</span>
            {posted && <span className="text-muted"> · posted {day(posted)}</span>}
            <span className="text-muted">
              {" "}
              · {ln.account_name ?? "—"}
              {ln.person ? ` · ${ln.person}` : ""}
            </span>
            {ln.description !== merchant && (
              <span className="block font-mono text-xs text-muted">{ln.description}</span>
            )}
          </span>
        </span>
        <span className="num">{showAmount(ln.amount)}</span>
      </div>
      {(ln.statement_file_id || source) && (
        <div className="mt-0.5 flex flex-wrap gap-x-4 pl-7 text-xs">
          {ln.statement_file_id && (
            <a
              className="text-primary underline"
              href={statementPageUrl(ln.statement_file_id, ln.page)}
              target="_blank"
              rel="noreferrer"
            >
              Open the statement{ln.page ? `, page ${ln.page}` : ""}
            </a>
          )}
          {source && (
            <button
              type="button"
              className="text-primary underline"
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              {open ? "Hide details" : "More details"}
            </button>
          )}
        </div>
      )}
      {open && source && <LineDetails id={ln.transaction_id} source={source} />}
    </li>
  );
}

const SECTION: Record<string, string> = {
  payment: "Payment",
  purchase: "Purchase",
  fee: "Fee",
  interest: "Interest",
  credit: "Money in",
  debit: "Money out",
  transfer: "Transfer",
};

function LineDetails({ id, source }: { id: number; source: LineSourceFn }) {
  const q = useQuery({ queryKey: ["line-source", source.scope, id], queryFn: () => source.fetch(id) });
  if (q.error) return <p className="mt-2 pl-7 text-xs text-danger-ink">{(q.error as Error).message}</p>;
  const d = q.data;
  if (!d) return <p className="mt-2 pl-7 text-xs text-muted">Reading the statement…</p>;
  const facts: [string, string | null][] = [
    ["Date", fullDay(d.txn_date)],
    ["Posted", d.post_date ? fullDay(d.post_date) : null],
    [
      "Account",
      d.account_name ? `${d.account_name}${d.account_last4 ? ` ····${d.account_last4}` : ""}` : null,
    ],
    ["Card", d.cardholder ? `····${d.cardholder}` : null],
    ["Kind on the statement", d.section ? (SECTION[d.section] ?? d.section) : null],
    ["Reference", d.pay_reference],
    ["Note", d.notes],
    [
      "Statement",
      d.file_name
        ? `${d.file_name}${d.period_start && d.period_end ? ` (${day(d.period_start)} to ${fullDay(d.period_end)})` : ""}`
        : null,
    ],
    ["Where", d.page ? `page ${d.page}, line ${d.line_no}` : null],
  ];
  return (
    <div
      className="mt-2 ml-7 space-y-3 rounded-xl bg-surface p-3 text-xs"
      aria-label={`Details of ${fullDay(d.txn_date)}`}
    >
      <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[max-content_1fr]">
        {facts
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
      </dl>
      {(d.note_from || d.note || d.note_person) && (
        <p className="rounded-lg bg-info-bg px-2 py-1.5">
          <strong>From the transfer email:</strong> {d.note_from ? `${d.note_from}` : ""}
          {d.note_person ? ` (${d.note_person})` : ""}
          {d.note ? ` · “${d.note}”` : ""}
        </p>
      )}
      {d.around.length > 0 && (
        <div>
          <p className="text-muted">
            On the statement (the line in bold, account and ID numbers cut to their last 4):
          </p>
          <pre className="mt-1 overflow-x-auto rounded-lg bg-ground p-2 font-mono leading-relaxed whitespace-pre-wrap">
            {d.around.map((a) => (
              <span key={a.line_no} className={a.is_line ? "block font-bold text-ink" : "block text-muted"}>
                {a.text || " "}
              </span>
            ))}
          </pre>
        </div>
      )}
      {d.unreadable && (
        <p className="text-attention-ink">
          The statement file couldn’t be read to show the text around the line.
        </p>
      )}
      {!d.around.length && d.text && (
        <p>
          <span className="text-muted">On the statement: </span>
          <span className="font-mono">{d.text}</span>
        </p>
      )}
      {d.similar.length > 0 && (
        <div>
          <p className="text-muted">The same merchant before:</p>
          <ul className="mt-1 space-y-0.5" aria-label="The same merchant before">
            {d.similar.map((x, i) => (
              <li key={i}>
                {fullDay(x.txn_date)} · <span className="num">{showAmount(x.amount)}</span> →{" "}
                <strong>{x.category_path ?? "—"}</strong>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
