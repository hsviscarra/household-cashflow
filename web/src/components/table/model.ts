import { type ReactNode } from "react";
import { type TableSort } from "../../prefs";

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

export const compare = (a: string | number, b: string | number) =>
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

export const amountOf = (text: string) =>
  text.trim() === "" || !Number.isFinite(Number(text)) ? undefined : Number(text);
