import type { ExploreResult } from "../api";
import { DIMENSIONS, MEASURES, cellText } from "../explore";

/** A view's table: rows, columns and their totals. `limit` shows only the first rows (Home). */
export default function ExploreTable({
  r,
  caption,
  limit,
}: {
  r: ExploreResult;
  caption: string;
  limit?: number;
}) {
  const rows = limit ? r.rows.slice(0, limit) : r.rows;
  const hidden = r.rows.length - rows.length;
  const text = (v: string) => cellText(r.measure, v);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="text-muted">
          <tr>
            <th scope="col" className="py-1 pr-3 text-left font-semibold">
              {DIMENSIONS[r.rows_by]}
            </th>
            {r.cols.map((c) => (
              <th key={c} scope="col" className="px-2 py-1 text-right font-semibold">
                {c}
              </th>
            ))}
            <th scope="col" className="py-1 pl-2 text-right font-semibold">
              {r.cols.length ? "Total" : MEASURES[r.measure]}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((name, i) => (
            <tr key={name}>
              <th scope="row" className="max-w-64 truncate py-1.5 pr-3 text-left font-medium" title={name}>
                {name}
              </th>
              {r.cells[i].slice(0, r.cols.length).map((v, j) => (
                <td key={r.cols[j]} className="num px-2 py-1.5 text-right">
                  {text(v)}
                </td>
              ))}
              <td className="num py-1.5 pl-2 text-right font-semibold">{text(r.row_totals[i])}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-line font-semibold">
            <th scope="row" className="py-1.5 pr-3 text-left">
              {r.measure === "average" ? "All lines" : "Total"}
              {hidden > 0 && <span className="font-normal text-muted"> · {hidden} more rows</span>}
            </th>
            {r.col_totals.map((v, j) => (
              <td key={r.cols[j]} className="num px-2 py-1.5 text-right">
                {text(v)}
              </td>
            ))}
            <td className="num py-1.5 pl-2 text-right">{text(r.total)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
