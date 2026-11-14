import { type RuleInput, type Owner, type MatchType, fetchCategories, testRule } from "../../api";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { MATCH_LABEL, Panel } from "./shared";
import CategoryPicker from "../../components/CategoryPicker";

export function RuleForm(props: { busy: boolean; onCancel: () => void; onSubmit: (b: RuleInput) => void }) {
  const [pattern, setPattern] = useState("");
  const [person, setPerson] = useState<Owner | "">("");
  const [merchantName, setMerchantName] = useState("");
  const [matchType, setMatchType] = useState<MatchType>("contains");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [priority, setPriority] = useState(50);
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
  return (
    <form
      className="grid gap-4 md:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (categoryId === "") return;
        props.onSubmit({
          pattern: pattern.trim(),
          match_type: matchType,
          category_id: categoryId,
          priority,
          amount_min: amountMin.trim() || null,
          amount_max: amountMax.trim() || null,
          set_person: person || null,
          merchant_name: merchantName.trim() || null,
        });
      }}
    >
      <label className="md:col-span-2">
        <span className="label">Pattern in the statement description</span>
        <input
          className="field font-mono"
          required
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
          {(Object.keys(MATCH_LABEL) as MatchType[]).map((m) => (
            <option key={m} value={m}>
              {MATCH_LABEL[m]}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Priority (lower runs first)</span>
        <input
          className="field num"
          type="number"
          min={0}
          max={1000}
          value={priority}
          onChange={(e) => setPriority(Number(e.target.value))}
        />
      </label>
      <div className="md:col-span-2">
        <CategoryPicker
          label="Category"
          value={categoryId}
          onChange={setCategoryId}
          groups={groups}
          required
        />
      </div>
      <label>
        <span className="label">Only amounts from (optional)</span>
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
        <span className="label">Up to (optional)</span>
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
      <p className="text-sm text-muted md:col-span-4">
        Amounts are compared without their sign: “up to 299.99” catches a 104.11 payment, not a 505.19 one.
      </p>
      <label>
        <span className="label">Also set person (optional)</span>
        <select className="field" value={person} onChange={(e) => setPerson(e.target.value as Owner | "")}>
          <option value="">Keep the account’s</option>
          <option value="Hernan">Hernan</option>
          <option value="Lauren">Lauren</option>
          <option value="Joint">Joint</option>
        </select>
      </label>
      <label>
        <span className="label">Show merchant as (optional)</span>
        <input
          className="field"
          maxLength={100}
          value={merchantName}
          onChange={(e) => setMerchantName(e.target.value)}
        />
      </label>
      <div className="flex items-end gap-2 md:col-span-2">
        <button type="submit" className="btn btn-primary" disabled={props.busy}>
          Add rule
        </button>
        <button type="button" className="btn btn-quiet" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function RuleTester() {
  const [text, setText] = useState("");
  const [amount, setAmount] = useState("");
  const tester = useMutation({ mutationFn: testRule });
  const result = tester.data;
  return (
    <Panel>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) tester.mutate({ description: text.trim(), amount: amount.trim() || undefined });
        }}
      >
        <label className="min-w-56 flex-1">
          <span className="label">Try a statement description</span>
          <input
            className="field font-mono"
            placeholder="UBER EATS SAN JOSE"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <label className="w-36">
          <span className="label">Amount (optional)</span>
          <input
            className="field num"
            type="number"
            step="0.01"
            inputMode="decimal"
            placeholder="-104.11"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-secondary" disabled={tester.isPending}>
          Test rules
        </button>
      </form>
      <div aria-live="polite" className="mt-3 min-h-6">
        {tester.error && <span className="text-danger-ink">{tester.error.message}</span>}
        {result &&
          (result.rule ? (
            <span>
              Matches <code className="font-mono">{result.rule.pattern}</code> →{" "}
              <strong>{result.rule.category_path}</strong>
            </span>
          ) : (
            <span className="rounded-full bg-attention-bg px-3 py-1 text-attention-ink">
              No rule matches; this line would go to review.
            </span>
          ))}
      </div>
    </Panel>
  );
}
