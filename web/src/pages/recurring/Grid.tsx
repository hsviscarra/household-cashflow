import { type GridRow, type GridCell } from "../../api";
import { type Selected } from "./shared";
import { Fragment } from "react";
import { money, num, monthLong } from "../../money";

export function Block({
  title,
  rows,
  selected,
  onSelect,
}: {
  title: string;
  rows: GridRow[];
  selected: Selected;
  onSelect: (s: Selected) => void;
}) {
  if (!rows.length) return null;
  let group = "";
  return (
    <tbody className="divide-y divide-line">
      <tr>
        <th
          colSpan={13}
          scope="rowgroup"
          className="bg-ground px-3 pb-1 pt-4 text-left font-display text-base font-bold"
        >
          <span className="sticky left-3">{title}</span>
        </th>
      </tr>
      {rows.map((r) => {
        const header = r.group !== group;
        group = r.group;
        return (
          <Fragment key={r.template_id}>
            {header && (
              <tr>
                <td
                  colSpan={13}
                  className="px-3 pt-2 text-xs font-semibold uppercase tracking-wide text-muted"
                >
                  <span className="sticky left-3">{r.group}</span>
                </td>
              </tr>
            )}
            <tr className={r.is_active ? "" : "text-muted"}>
              <th scope="row" className="sticky left-0 bg-ground px-3 py-1.5 text-left font-medium">
                <button
                  className="text-left underline-offset-2 hover:underline"
                  aria-pressed={selected?.kind === "template" && selected.template === r.template_id}
                  onClick={() => onSelect({ kind: "template", template: r.template_id })}
                >
                  {r.name}
                </button>
              </th>
              {r.cells.map((c) => (
                <td key={c.month} className="px-0.5 py-1 text-right">
                  <CellButton
                    row={r}
                    c={c}
                    active={
                      selected?.kind === "cell" &&
                      selected.template === r.template_id &&
                      selected.month === c.month
                    }
                    onClick={() => onSelect({ kind: "cell", template: r.template_id, month: c.month })}
                  />
                </td>
              ))}
            </tr>
          </Fragment>
        );
      })}
    </tbody>
  );
}

export const STATUS_WORD: Record<GridCell["status"], string> = {
  matched: "paid",
  planned: "expected",
  skipped: "skipped",
  not_generated: "not generated",
  none: "",
};

export function CellButton({
  row,
  c,
  active,
  onClick,
}: {
  row: GridRow;
  c: GridCell;
  active: boolean;
  onClick: () => void;
}) {
  if (c.status === "none") return <span className="sr-only">none</span>;
  const shown =
    c.status === "matched"
      ? money(Math.abs(num(c.actual)))
      : c.status === "planned"
        ? money(Math.abs(num(c.expected)))
        : c.status === "skipped"
          ? "skipped"
          : "—";
  const look =
    c.status === "matched" ? "text-ink" : c.status === "planned" ? "italic text-muted" : "text-xs text-muted";
  return (
    <button
      className={`num w-full whitespace-nowrap rounded-lg px-1 py-1 text-right hover:bg-surface ${active ? "bg-info-bg" : ""} ${look}`}
      aria-label={`${row.name}, ${monthLong(c.month)}: ${shown === "—" ? "" : `${shown}, `}${STATUS_WORD[c.status]}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {c.is_override && c.status !== "matched" && <span aria-hidden>• </span>}
      {shown}
    </button>
  );
}

export function TotalRow({
  label,
  values,
  signedValues,
}: {
  label: string;
  values: number[];
  signedValues?: boolean;
}) {
  return (
    <tr>
      <th scope="row" className="sticky left-0 bg-ground px-3 py-1.5 text-left">
        {label}
      </th>
      {values.map((v, i) => (
        <td key={i} className="num whitespace-nowrap px-1.5 py-1.5 text-right">
          {signedValues ? (v < 0 ? `−${money(-v)}` : money(v)) : money(v)}
        </td>
      ))}
    </tr>
  );
}
