import { type Column } from "./model";
import { useDensity } from "../../prefs";

/** Which columns show, and in what order: a checkbox each, and up and down to move it. */
export function ColumnMenu<T>({
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
