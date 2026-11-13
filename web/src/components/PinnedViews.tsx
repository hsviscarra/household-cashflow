import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchExplore } from "../api";
import { request, type SavedView } from "../explore";
import { localToday } from "../money";
import ExploreTable from "./ExploreTable";

// Views pinned from Explore (ADR-099): each one on Home with its first rows and its total.
const ROWS_ON_HOME = 6;

export default function PinnedViews({ views }: { views: SavedView[] }) {
  const today = localToday();
  const results = useQueries({
    queries: views.map((v) => ({
      queryKey: ["explore", request(v.spec, today)],
      queryFn: () => fetchExplore(request(v.spec, today)),
      staleTime: 5 * 60_000,
    })),
  });
  return (
    <section className="card h-full" aria-labelledby="pinned">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="pinned" className="font-display text-xl font-bold">
          Your views
        </h2>
        <Link to="/explore" className="text-sm font-semibold text-primary">
          Explore →
        </Link>
      </div>
      <div className="mt-3 space-y-5">
        {views.map((v, i) => {
          const q = results[i];
          return (
            <div key={v.name}>
              <h3 className="font-semibold">{v.name}</h3>
              {q.error && <p className="text-sm text-muted">Not available right now.</p>}
              {!q.data && !q.error && <p className="text-sm text-muted">Loading…</p>}
              {q.data &&
                (q.data.rows.length ? (
                  <ExploreTable r={q.data} caption={v.name} limit={ROWS_ON_HOME} />
                ) : (
                  <p className="text-sm text-muted">No spending matches this view.</p>
                ))}
            </div>
          );
        })}
      </div>
    </section>
  );
}
