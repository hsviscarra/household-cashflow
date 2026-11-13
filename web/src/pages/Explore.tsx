import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchCategories, fetchExplore, type ExploreResult } from "../api";
import { Legend, StackedColumns } from "../components/charts";
import ExploreTable from "../components/ExploreTable";
import {
  DEFAULT_VIEW,
  DIMENSIONS,
  MAX_VIEWS,
  MEASURES,
  PERIODS,
  VIEWS_KEY,
  cellText,
  exploreCsv,
  request,
  savedViews,
  viewSpec,
  type SavedView,
  type ViewSpec,
} from "../explore";
import { downloadText } from "../csv";
import { localToday, num } from "../money";
import { useSettings } from "../prefs";

// Explore (ADR-099, plan item B4): build your own view of spending, see it as a table or a
// chart, keep it by name and pin it to Home.

const PALETTE = ["groceries", "transport", "dining", "health", "shopping", "services", "delivery"].map(
  (c) => `var(--color-cat-${c})`,
);
const CHART_ROWS = PALETTE.length; // rows drawn as their own colour; the rest stay in the table
const PEOPLE: ViewSpec["person"][] = ["Both", "Hernan", "Lauren", "Joint"];

/** "Amount spent by group and month, last 6 months" */
export function viewTitle(spec: ViewSpec): string {
  const by = `${DIMENSIONS[spec.rows].toLowerCase()}${spec.cols === "none" ? "" : ` and ${DIMENSIONS[spec.cols].toLowerCase()}`}`;
  const who = spec.person === "Both" ? "" : `, ${spec.person}`;
  return `${MEASURES[spec.measure]} by ${by}, ${PERIODS[spec.period].toLowerCase()}${who}`;
}

export default function ExplorePage() {
  const { settings, set } = useSettings();
  const views = savedViews(settings[VIEWS_KEY]);
  const [spec, setSpec] = useState<ViewSpec>(() => viewSpec(settings["explore:last"] ?? DEFAULT_VIEW));
  const [name, setName] = useState("");
  const change = (part: Partial<ViewSpec>) => {
    const next = viewSpec({ ...spec, ...part });
    setSpec(next);
    set("explore:last", next);
  };
  const today = localToday();
  const q = useQuery({
    queryKey: ["explore", request(spec, today)],
    queryFn: () => fetchExplore(request(spec, today)),
    placeholderData: (old) => old,
  });
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const r = q.data;
  const title = viewTitle(spec);
  const saveViews = (list: SavedView[]) => set(VIEWS_KEY, list.slice(0, MAX_VIEWS));
  const save = () => {
    const as = name.trim();
    if (!as) return;
    const was = views.find((v) => v.name === as);
    saveViews([{ name: as, spec, pinned: was?.pinned ?? false }, ...views.filter((v) => v.name !== as)]);
    setName("");
  };
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">Explore your spending</h1>
      <p className="mt-2 max-w-3xl text-lg text-muted">
        Pick what to measure, what goes in the rows and the columns, and a period. Keep a view by name and pin
        it to Home.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-3" role="group" aria-label="The view">
        <Pick
          label="Measure"
          value={spec.measure}
          options={MEASURES}
          onChange={(measure) => change({ measure })}
        />
        <Pick label="Rows" value={spec.rows} options={DIMENSIONS} onChange={(rows) => change({ rows })} />
        <Pick
          label="Columns"
          value={spec.cols}
          options={{ none: "Nothing", ...DIMENSIONS }}
          disabled={[spec.rows]}
          onChange={(cols) => change({ cols })}
        />
        <Pick
          label="Period"
          value={spec.period}
          options={PERIODS}
          onChange={(period) => change({ period })}
        />
        <label>
          <span className="label">Who</span>
          <select
            className="field !w-32"
            value={spec.person}
            onChange={(e) => change({ person: e.target.value as ViewSpec["person"] })}
          >
            {PEOPLE.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Only the group</span>
          <select
            className="field !w-48"
            value={spec.group_id ?? ""}
            onChange={(e) => change({ group_id: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">Every group</option>
            {(groups.data ?? [])
              .filter((g) => g.kind === "expense")
              .map((g) => (
                <option key={g.category_id} value={g.category_id}>
                  {g.name}
                </option>
              ))}
          </select>
        </label>
        <Pick
          label="Show"
          value={spec.show}
          options={{ table: "Table", chart: "Chart" }}
          onChange={(show) => change({ show })}
        />
      </div>

      {q.error && (
        <p role="alert" className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          {(q.error as Error).message}
        </p>
      )}
      {!r && !q.error && <p className="mt-6 text-muted">Adding it up…</p>}
      {r && (
        <section className="card mt-6" aria-labelledby="view">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 id="view" className="font-display text-xl font-bold">
              {title}
            </h2>
            <button
              type="button"
              className="btn btn-quiet h-9 px-3 text-sm"
              onClick={() => downloadText("explore.csv", exploreCsv(r))}
            >
              Download CSV
            </button>
          </div>
          {r.rows.length === 0 ? (
            <p className="mt-3 text-muted">No spending matches this view.</p>
          ) : (
            <div className="mt-3">
              {spec.show === "chart" && <Chart r={r} title={title} />}
              <details open={spec.show === "table"} className={spec.show === "chart" ? "mt-2 text-sm" : ""}>
                <summary className={spec.show === "chart" ? "cursor-pointer text-muted" : "sr-only"}>
                  The numbers
                </summary>
                <ExploreTable r={r} caption={title} />
              </details>
              {r.folded > 0 && (
                <p className="mt-2 text-sm text-muted">
                  The {r.folded} smallest rows are added together as “Everything else”.
                </p>
              )}
            </div>
          )}
        </section>
      )}

      <section className="card mt-6" aria-labelledby="saved">
        <h2 id="saved" className="font-display text-xl font-bold">
          Saved views
        </h2>
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <label>
            <span className="label">Save this view as</span>
            <input
              className="field !w-64"
              maxLength={60}
              placeholder="Groceries by month"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-secondary" disabled={!name.trim()}>
            Save view
          </button>
        </form>
        {views.length === 0 ? (
          <p className="mt-3 text-sm text-muted">Nothing saved yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line text-sm" aria-label="Saved views">
            {views.map((v) => (
              <li key={v.name} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                <span>
                  <button
                    type="button"
                    className="font-semibold text-primary underline"
                    aria-label={`Open ${v.name}`}
                    onClick={() => change(v.spec)}
                  >
                    {v.name}
                  </button>{" "}
                  <span className="text-muted">· {viewTitle(v.spec)}</span>
                </span>
                <span className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      aria-label={`Pin ${v.name} to Home`}
                      checked={v.pinned}
                      onChange={(e) =>
                        saveViews(views.map((x) => (x === v ? { ...x, pinned: e.target.checked } : x)))
                      }
                    />
                    On Home
                  </label>
                  <button
                    type="button"
                    className="text-primary underline"
                    aria-label={`Delete ${v.name}`}
                    onClick={() => saveViews(views.filter((x) => x !== v))}
                  >
                    Delete
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}

/** Columns along the bottom (or the rows, without columns), the biggest rows stacked in colour. */
function Chart({ r, title }: { r: ExploreResult; title: string }) {
  const wide = r.cols.length > 0;
  const shown = r.rows.slice(0, CHART_ROWS);
  const data = wide
    ? r.cols.map((c, j) => ({
        key: c,
        label: c,
        segments: shown.map((name, i) => ({
          key: name,
          color: PALETTE[i],
          value: Math.max(0, num(r.cells[i][j])),
        })),
        tooltip: (
          <>
            <strong>{c}</strong>
            {shown.map((name, i) =>
              num(r.cells[i][j]) ? (
                <span key={name} className="num block">
                  {name} {cellText(r.measure, r.cells[i][j])}
                </span>
              ) : null,
            )}
            <span className="num block font-semibold">{cellText(r.measure, r.col_totals[j])}</span>
          </>
        ),
      }))
    : r.rows.slice(0, 24).map((name, i) => ({
        key: name,
        label: name.length > 10 ? `${name.slice(0, 9)}…` : name,
        segments: [{ key: "value", color: "var(--color-primary)", value: Math.max(0, num(r.row_totals[i])) }],
        tooltip: (
          <>
            <strong>{name}</strong>
            <span className="num block font-semibold">{cellText(r.measure, r.row_totals[i])}</span>
          </>
        ),
      }));
  return (
    <div>
      <StackedColumns title={title} data={data} />
      {wide && <Legend items={shown.map((name, i) => ({ label: name, color: PALETTE[i] }))} />}
      {wide && r.rows.length > shown.length && (
        <p className="mt-1 text-sm text-muted">
          The chart draws the {shown.length} biggest rows; the table below has all {r.rows.length}.
        </p>
      )}
    </div>
  );
}

function Pick<K extends string>({
  label,
  value,
  options,
  onChange,
  disabled = [],
}: {
  label: string;
  value: K;
  options: Record<K, string>;
  onChange: (value: K) => void;
  disabled?: string[];
}) {
  return (
    <label>
      <span className="label">{label}</span>
      <select className="field !w-44" value={value} onChange={(e) => onChange(e.target.value as K)}>
        {(Object.keys(options) as K[]).map((k) => (
          <option key={k} value={k} disabled={disabled.includes(k)}>
            {options[k]}
          </option>
        ))}
      </select>
    </label>
  );
}
