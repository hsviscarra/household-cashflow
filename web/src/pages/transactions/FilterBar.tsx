import { SaveView } from "../../components/Personalize";
import { monthLong } from "../../money";
import { PERIODS, type Filters } from "./shared";

/** The filters above the transactions: month and period, account, category, an amount range,
 * search and two ticks. Each change goes to the address (`setParam`), so a view can be saved and
 * shared. `min` and `max` are the amounts as typed. */
export function FilterBar({
  month,
  months,
  f,
  min,
  max,
  accounts,
  groups,
  setParam,
}: {
  month: string;
  months: number;
  f: Filters;
  min: string;
  max: string;
  accounts: string[];
  groups: string[];
  setParam: (key: string, value: string | null) => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-end gap-3" role="group" aria-label="Filters">
      <label>
        <span className="label">Month</span>
        <input
          type="month"
          className="field w-44"
          value={month}
          onChange={(e) => e.target.value && setParam("month", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Period</span>
        <select
          className="field w-44"
          value={String(months)}
          onChange={(e) => setParam("months", e.target.value === "1" ? null : e.target.value)}
        >
          {Object.entries(PERIODS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Account</span>
        <select
          className="field w-48"
          value={f.account ?? ""}
          onChange={(e) => setParam("acct", e.target.value || null)}
        >
          <option value="">Any</option>
          {accounts.map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Category</span>
        <select
          className="field w-48"
          value={f.group ?? ""}
          onChange={(e) => setParam("cat", e.target.value || null)}
        >
          <option value="">Any</option>
          {groups.map((g) => (
            <option key={g}>{g}</option>
          ))}
        </select>
      </label>
      <fieldset className="flex items-end gap-1">
        <legend className="label">Amount</legend>
        <label>
          <span className="sr-only">From</span>
          <input
            className="field num w-24"
            inputMode="decimal"
            placeholder="from"
            value={min ?? ""}
            onChange={(e) => setParam("min", e.target.value.trim() || null)}
          />
        </label>
        <span className="pb-3 text-muted">–</span>
        <label>
          <span className="sr-only">Up to</span>
          <input
            className="field num w-24"
            inputMode="decimal"
            placeholder="up to"
            value={max ?? ""}
            onChange={(e) => setParam("max", e.target.value.trim() || null)}
          />
        </label>
      </fieldset>
      <label>
        <span className="label">Search</span>
        <input
          type="search"
          className="field w-64"
          value={f.q}
          placeholder="Description, merchant, note, amount"
          onChange={(e) => setParam("q", e.target.value)}
        />
      </label>
      <label className="flex h-11 items-center gap-2">
        <input
          type="checkbox"
          checked={f.todo}
          onChange={(e) => setParam("todo", e.target.checked ? "1" : null)}
        />
        Needs a category
      </label>
      <label className="flex h-11 items-center gap-2">
        <input
          type="checkbox"
          checked={f.note}
          onChange={(e) => setParam("note", e.target.checked ? "1" : null)}
        />
        Has a note
      </label>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <SaveView month={monthLong(`${month}-01`)} />
      </div>
    </div>
  );
}
