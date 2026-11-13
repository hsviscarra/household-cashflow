import { Fragment, useState, type ReactNode } from "react";

import { money } from "../money";
import { useDensity, useTableLayout, type TableSort } from "../prefs";

// One table for every page (ADR-091, plan item B1): the person chooses the columns and their
// order, sorts by any column that can be sorted, groups rows with subtotals, and sees a totals
// row. The layout is theirs and follows them (prefs). Pages describe their columns; this draws.

export type Column<T> = {
  id: string;
  label: string;
  cell: (row: T) => ReactNode;
  /** What to sort by; a column without it can't be sorted. */
  sort?: (row: T) => string | number;
  /** The amount to add up in subtotals and the totals row. */
  total?: (row: T) => number;
  /** What to group by; a column without it isn't offered in "Group by". */
  group?: (row: T) => string;
  align?: "right";
  /** Drawn in the header instead of the label (a "tick all" box); the label still names it. */
  header?: ReactNode;
  /** The row's day (YYYY-MM-DD); with it the filter bar offers "from" and "to". */
  date?: (row: T) => string;
  /** Always shown and not in the column list: before the chosen columns (the row's name), or
   * with "end" after them (the amount, the row's actions). */
  fixed?: boolean | "end";
};

type Props<T> = {
  /** The settings key: one layout per table and person. */
  table: string;
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  /** Column ids shown until the person chooses. */
  defaults?: string[];
  defaultSort?: TableSort;
  /** A class for a row (a line that was split reads as struck out). */
  rowClass?: (row: T) => string;
  /** Something to draw under a row across the whole table (its editor), or null. */
  expanded?: (row: T) => ReactNode | null;
  /** The words a row is found by; with it the table gets a "Find in this table" box. */
  search?: (row: T) => string;
  /** A filter bar built from the columns (ADR-101): one value of any column that can be
   * grouped, an amount range on the first column that is totalled, and a date range when a
   * column has a date. Not remembered: a filter is for the question of the moment. */
  filter?: boolean;
  /** Rows can be ticked: the table adds the tick column, totals what is ticked and shows the
   * page's actions for those rows (ADR-093). The page owns which rows are ticked. */
  select?: {
    ticked: Set<string | number>;
    onChange: (ticked: Set<string | number>) => void;
    /** What the row is called in "Tick …". */
    name: (row: T) => string;
    /** Buttons or pickers that act on the ticked rows. */
    actions?: (rows: T[]) => ReactNode;
    /** In place of the plain sums: for example out, in and net. */
    summary?: (rows: T[]) => ReactNode;
  };
};

export type TableFilter = {
  column?: string; // a column that can be grouped…
  value?: string; // …and the one value of it to keep
  min?: number; // on the size of the amount, whatever its sign
  max?: number;
  from?: string; // days, YYYY-MM-DD, both included
  to?: string;
};

/** The rows a filter keeps. Each part only applies when it is filled in. */
export function filtered<T>(rows: T[], columns: Column<T>[], f: TableFilter): T[] {
  const by = f.value ? columns.find((c) => c.id === f.column)?.group : undefined;
  const amount = columns.find((c) => c.total)?.total;
  const day = columns.find((c) => c.date)?.date;
  return rows.filter((r) => {
    if (by && by(r) !== f.value) return false;
    if (amount && f.min !== undefined && Math.abs(amount(r)) < f.min) return false;
    if (amount && f.max !== undefined && Math.abs(amount(r)) > f.max) return false;
    if (day && f.from && day(r) < f.from) return false;
    if (day && f.to && day(r) > f.to) return false;
    return true;
  });
}

/** Every word typed must appear in the row's words, in any order and any case. */
export function found<T>(rows: T[], words: (row: T) => string, typed: string): T[] {
  const wanted = typed.toLowerCase().split(/\s+/).filter(Boolean);
  if (!wanted.length) return rows;
  return rows.filter((r) => {
    const text = words(r).toLowerCase();
    return wanted.every((w) => text.includes(w));
  });
}

const compare = (a: string | number, b: string | number) =>
  typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));

/** Rows in the chosen order; without a sort they stay as given. */
export function sorted<T>(rows: T[], columns: Column<T>[], sort: TableSort | null): T[] {
  const by = columns.find((c) => c.id === sort?.id)?.sort;
  if (!by || !sort) return rows;
  const sign = sort.dir === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => sign * compare(by(a), by(b)));
}

/** Rows split by the grouping column, groups in name order; one unnamed group when not grouped. */
export function grouped<T>(rows: T[], by?: (row: T) => string): { name: string | null; rows: T[] }[] {
  if (!by) return [{ name: null, rows }];
  const groups = new Map<string, T[]>();
  for (const r of rows) groups.set(by(r), [...(groups.get(by(r)) ?? []), r]);
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, list]) => ({ name, rows: list }));
}

export default function DataTable<T>({
  table,
  caption,
  columns,
  rows,
  rowKey,
  defaults,
  defaultSort,
  rowClass,
  expanded,
  search,
  filter,
  select,
}: Props<T>) {
  const [typed, setTyped] = useState("");
  const [only, setOnly] = useState<TableFilter>({});
  const all = rows;
  rows = filtered(search ? found(all, search, typed) : all, columns, filter ? only : {});
  const pickable = columns.filter((c) => !c.fixed);
  const [layout, setLayout] = useTableLayout(
    table,
    pickable.map((c) => c.id),
    defaults,
    columns.filter((c) => c.fixed).map((c) => c.id),
  );
  const byId = new Map(columns.map((c) => [c.id, c]));
  const tick: Column<T>[] = select
    ? [
        {
          id: "__tick",
          label: "Tick",
          fixed: true,
          header: (
            <input
              type="checkbox"
              aria-label="Tick every row shown"
              checked={rows.length > 0 && rows.every((r) => select.ticked.has(rowKey(r)))}
              onChange={(e) => select.onChange(new Set(e.target.checked ? rows.map(rowKey) : []))}
            />
          ),
          cell: (r) => (
            <input
              type="checkbox"
              aria-label={`Tick ${select.name(r)}`}
              checked={select.ticked.has(rowKey(r))}
              onChange={() => {
                const next = new Set(select.ticked);
                if (!next.delete(rowKey(r))) next.add(rowKey(r));
                select.onChange(next);
              }}
            />
          ),
        },
      ]
    : [];
  const chosen = select ? all.filter((r) => select.ticked.has(rowKey(r))) : [];
  const shown = [
    ...tick,
    ...columns.filter((c) => c.fixed && c.fixed !== "end"),
    ...layout.columns.map((id) => byId.get(id)!),
    ...columns.filter((c) => c.fixed === "end"),
  ];
  const sort = layout.sort ?? defaultSort ?? null;
  const groupBy = layout.group ? byId.get(layout.group) : undefined;
  const groups = grouped(sorted(rows, columns, sort), groupBy?.group);
  const hasTotals = shown.some((c) => c.total);

  const toggleSort = (id: string) =>
    setLayout({ sort: { id, dir: sort?.id === id && sort.dir === "asc" ? "desc" : "asc" } });
  // The group's or the table's name goes in the first column that holds text, not a tick box.
  const named = Math.max(
    shown.findIndex((c) => !c.header),
    0,
  );
  const sums = (list: T[], first: ReactNode) =>
    shown.map((c, i) => (
      <td key={c.id} className={`num px-3 py-2 ${c.align === "right" ? "text-right" : ""}`}>
        {i === named ? first : c.total ? money(list.reduce((t, r) => t + c.total!(r), 0)) : ""}
      </td>
    ));

  return (
    <div>
      {filter && (
        <FilterBar columns={columns} rows={all} value={only} onChange={setOnly} kept={rows.length} />
      )}
      <div className="flex flex-wrap items-center justify-end gap-3">
        {search && (
          <label className="mr-auto flex items-center gap-2 text-sm">
            <span className="sr-only">Find in this table</span>
            <input
              type="search"
              className="field h-10 !w-64"
              placeholder="Find in this table"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
            />
            {typed && (
              <span className="text-muted" role="status">
                {rows.length} of {all.length}
              </span>
            )}
          </label>
        )}
        {columns.some((c) => c.group) && (
          <label className="flex items-center gap-2 text-sm">
            Group by
            <select
              className="field h-10 !w-auto"
              value={layout.group ?? ""}
              onChange={(e) => setLayout({ group: e.target.value || null })}
            >
              <option value="">Nothing</option>
              {columns
                .filter((c) => c.group)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
            </select>
          </label>
        )}
        <ColumnMenu
          columns={pickable}
          shown={layout.columns}
          onChange={(ids) => setLayout({ columns: ids })}
        />
      </div>
      {select && chosen.length > 0 && (
        <div
          className="mt-3 flex flex-wrap items-center gap-3 rounded-[10px] bg-info-bg px-3 py-2 text-sm"
          role="status"
        >
          <span className="font-semibold">{chosen.length} ticked</span>
          {select.summary
            ? select.summary(chosen)
            : columns
                .filter((c) => c.total)
                .map((c) => (
                  <span key={c.id}>
                    {c.label}{" "}
                    <span className="num font-semibold">
                      {money(chosen.reduce((t, r) => t + c.total!(r), 0))}
                    </span>
                  </span>
                ))}
          {select.actions?.(chosen)}
          <button
            type="button"
            className="btn btn-quiet ml-auto h-8 px-3"
            onClick={() => select.onChange(new Set())}
          >
            Clear
          </button>
        </div>
      )}
      <div className="mt-3 overflow-x-auto rounded-[14px] border border-line bg-ground">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="text-muted">
            <tr>
              {shown.map((c) => (
                <th
                  key={c.id}
                  scope="col"
                  aria-sort={
                    sort?.id === c.id ? (sort.dir === "asc" ? "ascending" : "descending") : undefined
                  }
                  className={`px-3 py-2 font-semibold ${c.align === "right" ? "text-right" : "text-left"}`}
                >
                  {c.header ? (
                    c.header
                  ) : c.sort ? (
                    <button
                      type="button"
                      className="font-semibold hover:text-ink"
                      onClick={() => toggleSort(c.id)}
                    >
                      {c.label}
                      <span aria-hidden="true">
                        {sort?.id === c.id ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
                      </span>
                    </button>
                  ) : (
                    c.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {groups.map((g) => (
              <Fragment key={g.name ?? ""}>
                {g.name !== null && (
                  <tr className="bg-surface font-semibold">
                    {sums(
                      g.rows,
                      <>
                        {g.name} <span className="font-normal text-muted">· {g.rows.length}</span>
                      </>,
                    )}
                  </tr>
                )}
                {g.rows.map((r) => {
                  const under = expanded?.(r) ?? null;
                  return (
                    <Fragment key={rowKey(r)}>
                      <tr className={rowClass?.(r)}>
                        {shown.map((c) => (
                          <td
                            key={c.id}
                            className={`px-3 py-2 align-top ${c.align === "right" ? "num text-right" : ""}`}
                          >
                            {c.cell(r)}
                          </td>
                        ))}
                      </tr>
                      {under !== null && (
                        <tr>
                          <td colSpan={shown.length} className="bg-surface px-4 py-4">
                            {under}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </Fragment>
            ))}
          </tbody>
          {hasTotals && rows.length > 0 && (
            <tfoot>
              <tr className="border-t border-line font-semibold">
                {sums(
                  rows,
                  <>
                    Total <span className="font-normal text-muted">· {rows.length}</span>
                  </>,
                )}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

/** Which columns show, and in what order: a checkbox each, and up and down to move it. */
function ColumnMenu<T>({
  columns,
  shown,
  onChange,
}: {
  columns: Column<T>[];
  shown: string[];
  onChange: (ids: string[]) => void;
}) {
  const [density, setDensity] = useDensity();
  // Shown columns first, in their order; the hidden ones after, in the page's order.
  const listed = [
    ...shown.map((id) => columns.find((c) => c.id === id)!),
    ...columns.filter((c) => !shown.includes(c.id)),
  ];
  const move = (id: string, by: -1 | 1) => {
    const i = shown.indexOf(id);
    const next = [...shown];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    onChange(next);
  };
  return (
    <details className="relative">
      <summary className="btn btn-quiet h-10 cursor-pointer list-none px-4 text-sm">
        Columns &amp; rows
      </summary>
      <div className="absolute right-0 z-20 mt-2 w-72 space-y-4 rounded-2xl border border-line bg-ground p-4 shadow-lg">
        <fieldset>
          <legend className="label">Columns</legend>
          {listed.map((c) => {
            const at = shown.indexOf(c.id);
            return (
              <div key={c.id} className="flex items-center gap-1 py-0.5 text-sm">
                <label className="flex flex-1 items-center gap-2 py-1">
                  <input
                    type="checkbox"
                    checked={at >= 0}
                    onChange={(e) =>
                      onChange(e.target.checked ? [...shown, c.id] : shown.filter((x) => x !== c.id))
                    }
                  />
                  {c.label}
                </label>
                {at >= 0 && (
                  <>
                    <button
                      type="button"
                      className="btn btn-quiet h-8 w-8 p-0"
                      aria-label={`Move ${c.label} left`}
                      disabled={at === 0}
                      onClick={() => move(c.id, -1)}
                    >
                      ←
                    </button>
                    <button
                      type="button"
                      className="btn btn-quiet h-8 w-8 p-0"
                      aria-label={`Move ${c.label} right`}
                      disabled={at === shown.length - 1}
                      onClick={() => move(c.id, 1)}
                    >
                      →
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </fieldset>
        <fieldset>
          <legend className="label">Rows (every table)</legend>
          {(["comfortable", "compact"] as const).map((d) => (
            <label key={d} className="flex items-center gap-2 py-1 text-sm capitalize">
              <input type="radio" name="density" checked={density === d} onChange={() => setDensity(d)} />
              {d}
            </label>
          ))}
        </fieldset>
      </div>
    </details>
  );
}

const amountOf = (text: string) =>
  text.trim() === "" || !Number.isFinite(Number(text)) ? undefined : Number(text);

/** The filter bar: what the columns allow, and how many rows are left. */
function FilterBar<T>({
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
