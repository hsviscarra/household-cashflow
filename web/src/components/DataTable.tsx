import { Fragment, type ReactNode } from "react";

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
  /** Always shown, first, and not in the column list (the row's name). */
  fixed?: boolean;
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
};

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
}: Props<T>) {
  const pickable = columns.filter((c) => !c.fixed);
  const [layout, setLayout] = useTableLayout(
    table,
    pickable.map((c) => c.id),
    defaults,
  );
  const byId = new Map(columns.map((c) => [c.id, c]));
  const shown = [...columns.filter((c) => c.fixed), ...layout.columns.map((id) => byId.get(id)!)];
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
      <div className="flex flex-wrap items-center justify-end gap-3">
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
                {g.rows.map((r) => (
                  <tr key={rowKey(r)}>
                    {shown.map((c) => (
                      <td
                        key={c.id}
                        className={`px-3 py-2 align-top ${c.align === "right" ? "num text-right" : ""}`}
                      >
                        {c.cell(r)}
                      </td>
                    ))}
                  </tr>
                ))}
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
