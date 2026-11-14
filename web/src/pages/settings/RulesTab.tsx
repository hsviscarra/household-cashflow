import {
  type Rule,
  fetchRules,
  fetchCategories,
  createRule,
  updateRule,
  deleteRule,
  fetchRuleSuggestions,
  fetchSettings,
  type RuleSuggestion,
  putSetting,
} from "../../api";
import { money } from "../../money";
import { type Notify, useSave, Loading, Panel, MATCH_LABEL } from "./shared";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { RuleTester, RuleForm } from "./RuleForm";

/** "any amount", "up to 299.99", "from 300", "50 to 100" — on the amount without its sign. */
export function amountRange(r: Pick<Rule, "amount_min" | "amount_max">): string {
  const lo = r.amount_min ? money(r.amount_min) : null;
  const hi = r.amount_max ? money(r.amount_max) : null;
  if (lo && hi) return `${lo} to ${hi}`;
  if (lo) return `from ${lo}`;
  if (hi) return `up to ${hi}`;
  return "any amount";
}

// ---------------- merchant rules ----------------
export function appliedNote(r: Pick<Rule, "applied">): string {
  const n = r.applied ?? 0;
  return n ? ` It categorized ${n} ${n === 1 ? "line" : "lines"} that needed a category.` : "";
}

export function RulesTab({ notify }: { notify: Notify }) {
  const rules = useQuery({ queryKey: ["rules"], queryFn: fetchRules });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState("");
  // A saved rule also categorizes loaded and waiting lines, so those views refresh too.
  const reach = [["rules"], ["review"], ["transactions"], ["batch"]];
  const create = useSave(createRule, reach, notify);
  const update = useSave((a: { id: number; body: Partial<Rule> }) => updateRule(a.id, a.body), reach, notify);
  const remove = useSave(deleteRule, [["rules"]], notify);

  if (!rules.data || !cats.data) return <Loading what="merchant rules" error={rules.error ?? cats.error} />;
  const q = filter.trim().toUpperCase();
  const shown = q
    ? rules.data.filter(
        (r) => r.pattern.toUpperCase().includes(q) || r.category_path.toUpperCase().includes(q),
      )
    : rules.data;

  return (
    <div className="space-y-6">
      <RuleTester />
      <SuggestedRules notify={notify} reach={reach} />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="min-w-56 flex-1 md:max-w-sm">
          <span className="label">Filter rules</span>
          <input className="field" type="search" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </label>
        {!adding && (
          <button className="btn btn-primary" onClick={() => setAdding(true)}>
            Add rule
          </button>
        )}
      </div>

      {adding && (
        <Panel>
          <RuleForm
            busy={create.isPending}
            onCancel={() => setAdding(false)}
            onSubmit={(body) =>
              create.mutate(body, {
                onSuccess: (r) => {
                  setAdding(false);
                  notify(`Rule added: ${r.pattern} → ${r.category_path}.${appliedNote(r)}`);
                },
              })
            }
          />
        </Panel>
      )}

      <p className="text-sm text-muted">
        Rules run in priority order (lowest number first); the first active match wins. Matching ignores upper
        and lower case.
      </p>
      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full text-left">
          <thead className="bg-surface text-sm text-muted">
            <tr>
              <th className="px-4 py-3 font-semibold">Pattern</th>
              <th className="px-4 py-3 font-semibold">Match</th>
              <th className="px-4 py-3 font-semibold">Category</th>
              <th className="px-4 py-3 font-semibold">Amount</th>
              <th className="px-4 py-3 text-right font-semibold">Priority</th>
              <th className="px-4 py-3 font-semibold">Active</th>
              <th className="px-4 py-3">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {shown.map((r) => (
              <tr key={r.rule_id} className={r.is_active ? "" : "text-muted"}>
                <td className="px-4 py-2 font-mono text-sm">{r.pattern}</td>
                <td className="px-4 py-2 text-sm">{MATCH_LABEL[r.match_type]}</td>
                <td className="px-4 py-2">
                  {r.category_path}
                  {(r.set_person || r.merchant_name) && (
                    <span className="block text-sm text-muted">{alsoNote(r)}</span>
                  )}
                </td>
                <td className={`num px-4 py-2 text-sm ${r.amount_min || r.amount_max ? "" : "text-muted"}`}>
                  {amountRange(r)}
                </td>
                <td className="num px-4 py-2 text-right">{r.priority}</td>
                <td className="px-4 py-2">
                  <input
                    type="checkbox"
                    className="h-5 w-5"
                    aria-label={`Rule ${r.pattern} active`}
                    checked={r.is_active}
                    onChange={(e) =>
                      update.mutate(
                        { id: r.rule_id, body: { is_active: e.target.checked } },
                        {
                          onSuccess: (saved) =>
                            notify(
                              `Rule ${saved.is_active ? "turned on" : "turned off"}: ${saved.pattern}.${appliedNote(saved)}`,
                            ),
                        },
                      )
                    }
                  />
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    className="btn btn-danger h-9 px-4 text-sm"
                    aria-label={`Delete rule ${r.pattern}`}
                    onClick={() => {
                      if (!window.confirm(`Delete the rule "${r.pattern}"?`)) return;
                      remove.mutate(r.rule_id, {
                        onSuccess: () => notify(`Rule deleted: ${r.pattern}.`),
                      });
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {!shown.length && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-muted">
                  No rules match “{filter}”.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function alsoNote(r: Pick<Rule, "set_person" | "merchant_name">): string {
  const parts = [
    r.set_person && `person ${r.set_person}`,
    r.merchant_name && `name “${r.merchant_name}”`,
  ].filter(Boolean);
  return parts.length ? `Also sets ${parts.join(" and ")}` : "";
}

export const DISMISSED = "rule_suggestions_dismissed";

/** Merchants categorized the same way at least twice by hand, offered as rules (ADR-042). */
export function SuggestedRules({ notify, reach }: { notify: Notify; reach: string[][] }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["rules", "suggestions"], queryFn: fetchRuleSuggestions });
  const me = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const save = useSave(createRule, reach, notify);
  const raw = me.data?.settings[DISMISSED];
  const dismissed = Array.isArray(raw) ? (raw as string[]) : [];
  const shown = (list.data ?? []).filter((s) => !dismissed.includes(s.pattern));
  if (!shown.length) return null;
  const dismiss = (s: RuleSuggestion) =>
    putSetting(DISMISSED, [...dismissed, s.pattern].slice(-200)).then(() =>
      qc.invalidateQueries({ queryKey: ["settings"] }),
    );
  return (
    <section aria-label="Suggested rules" className="card space-y-3 p-5">
      <div>
        <h2 className="text-lg font-semibold">Suggested rules</h2>
        <p className="text-sm text-muted">
          You categorized these the same way more than once. Save one and the next statements get it by
          themselves.
        </p>
      </div>
      <ul className="divide-y divide-line">
        {shown.map((s) => (
          <li key={s.pattern} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="font-mono text-sm">{s.pattern}</p>
              <p className="text-sm text-muted">
                → {s.category_path}
                {s.person ? ` · ${s.person}` : ""} · {s.times} times · e.g. {s.example}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className="btn btn-primary h-9 px-4 text-sm"
                disabled={save.isPending}
                aria-label={`Save rule ${s.pattern}`}
                onClick={() =>
                  save.mutate(
                    {
                      pattern: s.pattern,
                      match_type: "contains",
                      category_id: s.category_id,
                      priority: 50,
                      set_person: s.person,
                    },
                    {
                      onSuccess: (r) =>
                        notify(`Rule added: ${r.pattern} → ${r.category_path}.${appliedNote(r)}`),
                    },
                  )
                }
              >
                Save rule
              </button>
              <button
                className="btn btn-quiet h-9 px-4 text-sm"
                aria-label={`Not now ${s.pattern}`}
                onClick={() => void dismiss(s)}
              >
                Not now
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
