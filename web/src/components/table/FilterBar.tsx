import { type Column, type TableFilter, amountOf } from "./model";

/** The filter bar: what the columns allow, and how many rows are left. */
export function FilterBar<T>({
  columns,
  rows,
  value,
  onChange,
  kept,
}: {
  columns: Column<T>[];
  rows: T[];
  value: TableFilter;
  onChange: (f: TableFilter) => void;
  kept: number;
}) {
  const groupable = columns.filter((c) => c.group);
  const by = groupable.find((c) => c.id === value.column);
  const values = by ? [...new Set(rows.map((r) => by.group!(r)))].sort((a, b) => a.localeCompare(b)) : [];
  const hasAmount = columns.some((c) => c.total);
  const hasDate = columns.some((c) => c.date);
  const active = Object.values(value).some((v) => v !== undefined && v !== "");
  return (
    <div className="mb-3 flex flex-wrap items-end gap-3 text-sm" role="group" aria-label="Filter">
      {groupable.length > 0 && (
        <>
          <label>
            <span className="label">Only where</span>
            <select
              className="field h-10 !w-40"
              value={value.column ?? ""}
              onChange={(e) => onChange({ ...value, column: e.target.value || undefined, value: undefined })}
            >
              <option value="">Any</option>
              {groupable.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          {by && (
            <label>
              <span className="label">is</span>
              <select
                className="field h-10 !w-48"
                aria-label={`${by.label} is`}
                value={value.value ?? ""}
                onChange={(e) => onChange({ ...value, value: e.target.value || undefined })}
              >
                <option value="">Choose</option>
                {values.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          )}
        </>
      )}
      {hasAmount && (
        <>
          <label>
            <span className="label">Amount from</span>
            <input
              className="field num h-10 !w-28"
              inputMode="decimal"
              onChange={(e) => onChange({ ...value, min: amountOf(e.target.value) })}
            />
          </label>
          <label>
            <span className="label">Amount to</span>
            <input
              className="field num h-10 !w-28"
              inputMode="decimal"
              onChange={(e) => onChange({ ...value, max: amountOf(e.target.value) })}
            />
          </label>
        </>
      )}
      {hasDate && (
        <>
          <label>
            <span className="label">From</span>
            <input
              type="date"
              className="field h-10"
              onChange={(e) => onChange({ ...value, from: e.target.value || undefined })}
            />
          </label>
          <label>
            <span className="label">To</span>
            <input
              type="date"
              className="field h-10"
              onChange={(e) => onChange({ ...value, to: e.target.value || undefined })}
            />
          </label>
        </>
      )}
      {active && (
        <span className="pb-2 text-muted" role="status">
          {kept} of {rows.length} rows
        </span>
      )}
    </div>
  );
}
