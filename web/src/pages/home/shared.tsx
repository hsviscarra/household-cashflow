import { useSettings } from "../../prefs";
import { localToday, addMonths } from "../../money";
import { type Projection } from "../../api";
import { type ExplainKey } from "../../explain";
import { type ReactNode } from "react";
import Info from "../../components/Info";
import { Link } from "react-router-dom";

// Home (ADR-027, ADR-073): how much money there is now, how the month is going, what you are
// building (net worth, investments, the house, goals) and what needs you, as widgets each person
// can hide and reorder ("Customize"). A month picker changes every block.

export const WIDGETS: Record<string, string> = {
  needs: "Needs you",
  kpis: "This month so far",
  safe: "Safe to spend",
  money: "Your money now",
  networth: "Net worth",
  cashflow: "Cash flow by month",
  investments: "Investments",
  budget: "Budget: planned vs actual",
  goals: "Goals",
  coming: "Coming up",
  where: "Where it went",
  inbox: "Inbox",
  views: "Your views (pinned on Explore)",
};

export const LAYOUT = 2;

// saved widget lists from before this layout start from the new default
export const ALL = Object.keys(WIDGETS);

// Widgets added after a person saved their list show up for them once, after the first two;
// hiding one afterwards sticks, because the list they save says which widgets it knew.
export const KNOWN_BEFORE = ALL.filter((w) => w !== "safe" && w !== "views");

export const NEW_AT = 2;

export const COMING_DAYS = 14;

/** The person's widgets in their order; every widget when nothing is saved. */
export function useWidgets(): [string[], (ids: string[]) => void] {
  const { settings, set } = useSettings();
  const home = settings.home as { widgets?: unknown; layout?: number; known?: unknown } | undefined;
  const saved = home?.layout === LAYOUT ? home.widgets : undefined;
  if (!Array.isArray(saved)) return [ALL, (ids) => set("home", { widgets: ids, layout: LAYOUT, known: ALL })];
  const shown = saved.filter((w): w is string => ALL.includes(w as string));
  const known = Array.isArray(home?.known) ? (home.known as string[]) : KNOWN_BEFORE;
  const fresh = ALL.filter((w) => !known.includes(w) && !shown.includes(w));
  return [
    [...shown.slice(0, NEW_AT), ...fresh, ...shown.slice(NEW_AT)],
    (ids) => set("home", { widgets: ids, layout: LAYOUT, known: ALL }),
  ];
}

export const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return localToday(d);
};

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** Bills and purchases due from today through the next two weeks. */
export function comingUp(p: Projection, today: string, days = COMING_DAYS) {
  const end = addDays(today, days);
  return p.months
    .flatMap((m) => m.items)
    .filter((i) => (i.kind === "fixed" || i.kind === "purchase") && i.day >= today && i.day <= end)
    .sort((a, b) => a.day.localeCompare(b.day));
}

export function Card({
  id,
  title,
  info,
  link,
  children,
}: {
  id: string;
  title: string;
  info?: ExplainKey;
  link?: [string, string];
  children: ReactNode;
}) {
  return (
    <section className="card h-full" aria-labelledby={id}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-center gap-2">
          <h2 id={id} className="font-display text-xl font-bold">
            {title}
          </h2>
          {info && <Info k={info} />}
        </span>
        {link && (
          <Link to={link[0]} className="text-sm font-semibold text-primary">
            {link[1]} →
          </Link>
        )}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export const monthEnd = (iso: string) => {
  const d = new Date(`${addMonths(iso, 1)}T00:00:00`);
  d.setDate(0);
  return localToday(d);
};
