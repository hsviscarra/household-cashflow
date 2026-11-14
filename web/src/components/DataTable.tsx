import { Fragment, useState, type ReactNode } from "react";
import { money } from "../money";
import { useTableLayout, type TableSort } from "../prefs";
import { type Column, type TableFilter, filtered, found, sorted, grouped } from "./table/model";
import { FilterBar } from "./table/FilterBar";
import { ColumnMenu } from "./table/ColumnMenu";

export { type Column, type TableFilter, filtered, found, sorted, grouped } from "./table/model";

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
