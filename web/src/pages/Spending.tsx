import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchSpending } from "../api";
import SpendingChart from "../components/SpendingChart";
import { localToday, money, monthLong, monthShort, num, parts } from "../money";
import { ExportLinks } from "../components/ExportLinks";
import KpiCard from "../components/KpiCard";
import { PersonNote, SaveView } from "../components/Personalize";
import { personParam, usePerson } from "../prefs";
import { GroupMap, Ideas, MerchantTable, ProductTable, VIEWS, ViewSwitch, type View } from "./SpendingParts";
import { type Drill, change, prevMonth, headline } from "./spending/shared";
import { CategoryTable, Breakdown, Lines } from "./spending/Parts";

export { compareWords, change, headline } from "./spending/shared";

const PERSON: Record<string, string> = { Joint: "Shared" };

const COUNTRY: Record<string, string> = { EC: "Ecuador", US: "United States" };

const FIXED: Record<string, string> = { fixed: "Fixed", variable: "Variable" };

export default function SpendingPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("month");
  const month = raw && /^\d{4}-\d{2}$/.test(raw) ? `${raw}-01` : null;
  const [person, , ready] = usePerson();
  const q = useQuery({
    queryKey: ["spending", month, person],
    queryFn: () => fetchSpending(month, personParam(person)),
    enabled: ready,
  });
  const [drill, setDrill] = useState<Drill>(null);
  const [open, setOpen] = useState<number | null>(null);
  const s = q.data;
  const view: View = (params.get("view") as View) in VIEWS ? (params.get("view") as View) : "groups";
  const g = params.get("g") === null ? null : Number(params.get("g"));
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v === null ? next.delete(k) : next.set(k, v)));
    setParams(next);
  };
  const go = (m: string) => {
    setDrill(null);
    setOpen(null);
    set({ month: m.slice(0, 7), g: null });
  };
  const who = personParam(person);
  const group = s?.groups.find((x) => x.group_id === g);
  const fixed = s?.fixed.find((x) => x.key === "fixed");
  const variable = s?.fixed.find((x) => x.key === "variable");
  const unexplained = s?.groups.find((x) => x.group_id === 0);
  const idx = s ? s.months.indexOf(s.month) : -1;

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">{s ? headline(s) : "Spending"}</h1>
      <p className="mt-2 text-lg text-muted">
        Expenses, fees and interest less refunds; transfers and card payments are left out, like the
        Overview’s spending view.
      </p>
      {s && s.source !== "none" && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <ExportLinks
            dataset="spending_lines"
            label={`${monthLong(s.month)} lines`}
            month={s.month.slice(0, 7)}
          />
          <SaveView month={monthLong(s.month)} />
        </div>
      )}
      <PersonNote person={person} />
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load spending: {(q.error as Error).message}
        </p>
      )}
      {!s && !q.error && <p className="mt-6 text-muted">Adding up the month…</p>}
      {s && s.source === "none" && (
        <p className="mt-6 rounded-2xl bg-info-bg px-5 py-4">
          No spending loaded yet.{" "}
          <Link className="text-primary underline" to="/import">
            Load the Excel history or upload statements
          </Link>
          .
        </p>
      )}
      {s && s.source !== "none" && (
        <>
          <div className="mt-6 flex flex-wrap items-end gap-3">
            <button
              className="btn btn-quiet h-11 px-3"
              disabled={idx < 0 || idx >= s.months.length - 1}
              onClick={() => go(s.months[idx + 1])}
            >
              ← Earlier
            </button>
            <label>
              <span className="label">Month</span>
              <select className="field w-52" value={s.month} onChange={(e) => go(e.target.value)}>
                {s.months.map((m) => (
                  <option key={m} value={m}>
                    {monthLong(m)}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="btn btn-quiet h-11 px-3"
              disabled={idx <= 0}
              onClick={() => go(s.months[idx - 1])}
            >
              Later →
            </button>
            {s.source === "excel" && (
              <span className="pill pill-muted">From the Cash Flow sheet: categories, no merchants</span>
            )}
            <div className="ml-auto">
              <ViewSwitch
                view={view}
                onChange={(v) => {
                  setDrill(null);
                  set({ view: v === "groups" ? null : v, pg: null });
                }}
              />
            </div>
          </div>

          <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiCard
              label="Spent"
              value={money(s.total.amount)}
              note={
                s.month.slice(0, 7) === localToday().slice(0, 7)
                  ? `${s.total.transactions} lines so far; the month isn't over`
                  : `${change(s.total.amount, s.total.prev)} vs ${monthShort(prevMonth(s.month))} · ${s.total.transactions} lines`
              }
            />
            <KpiCard
              label="Fixed"
              value={money(fixed?.amount ?? 0)}
              note={`${fixed?.transactions ?? 0} lines: mortgage, daycare, insurance, staff`}
            />
            <KpiCard
              label="Variable"
              value={money(variable?.amount ?? 0)}
              note={`${variable?.transactions ?? 0} lines: where savings usually are`}
            />
            <KpiCard
              label="Not yet explained"
              value={money(unexplained?.amount ?? 0)}
              note={`${unexplained?.transactions ?? 0} lines without a category`}
              tone={unexplained && num(unexplained.amount) > 0 ? "attention" : undefined}
            />
          </dl>
          <p className="mt-2 text-sm text-muted">
            vs {monthShort(s.month)} {parts(s.month).year - 1}: {change(s.total.amount, s.total.last_year)}
          </p>

          {view === "groups" && (
            <>
              <GroupMap
                s={s}
                onPick={(id) => {
                  setOpen(id);
                  set({ g: String(id) });
                }}
              />
              {group && s.source !== "excel" && (
                <>
                  <nav aria-label="Drill path" className="mt-6 flex flex-wrap items-center gap-2 text-sm">
                    <button
                      type="button"
                      className="font-semibold text-primary underline"
                      onClick={() => set({ g: null })}
                    >
                      All spending
                    </button>
                    <span aria-hidden className="text-muted">
                      ›
                    </span>
                    <strong aria-current="location">{group.name}</strong>
                    {group.name === "Groceries" && (
                      <Link
                        to={`/groceries?month=${s.month.slice(0, 7)}`}
                        className="btn btn-primary ml-auto h-9 px-4 text-sm"
                      >
                        What it bought, product by product →
                      </Link>
                    )}
                  </nav>
                  <MerchantTable
                    month={s.month}
                    person={who}
                    groupId={group.group_id}
                    title={`${group.name}: ${money(group.amount)} in ${monthLong(s.month)}`}
                    onOpen={(m) => setDrill({ title: m, filter: { merchant: m }, from: "merchants" })}
                  />
                  {drill?.from === "merchants" && (
                    <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
                  )}
                </>
              )}
              <h2 className="mt-10 font-display text-2xl font-bold">By category</h2>
              <CategoryTable s={s} open={open} setOpen={setOpen} setDrill={setDrill} />
              {drill?.from === "category" && (
                <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
              )}
            </>
          )}

          {view === "merchants" && (
            <>
              <MerchantTable
                month={s.month}
                person={who}
                groupId={group?.group_id}
                title={group ? `${group.name} merchants` : `Merchants in ${monthLong(s.month)}`}
                onOpen={(m) => setDrill({ title: m, filter: { merchant: m }, from: "merchants" })}
              />
              {group && (
                <button type="button" className="btn btn-quiet mt-2" onClick={() => set({ g: null })}>
                  Every group
                </button>
              )}
              {drill?.from === "merchants" && (
                <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
              )}
            </>
          )}

          {view === "products" && (
            <ProductTable month={s.month} group={params.get("pg")} onGroup={(pg) => set({ pg })} />
          )}

          {view === "fixed" && (
            <>
              <h2 className="mt-10 font-display text-2xl font-bold">Who, where, fixed or variable</h2>
              <div className="mt-3 grid gap-4 md:grid-cols-3">
                <Breakdown
                  title="By person"
                  slices={s.by_person}
                  names={PERSON}
                  total={s.total.amount}
                  onPick={(x) =>
                    setDrill({ title: `${PERSON[x.key] ?? x.key}`, filter: { person: x.key }, from: "who" })
                  }
                />
                <Breakdown
                  title="By country"
                  slices={s.by_country}
                  names={COUNTRY}
                  total={s.total.amount}
                  onPick={(x) =>
                    setDrill({ title: COUNTRY[x.key] ?? x.key, filter: { country: x.key }, from: "who" })
                  }
                />
                <Breakdown
                  title="Fixed or variable"
                  slices={s.fixed}
                  names={FIXED}
                  total={s.total.amount}
                  onPick={(x) =>
                    setDrill({
                      title: `${FIXED[x.key]} spending`,
                      filter: { fixed: x.key === "fixed" },
                      from: "who",
                    })
                  }
                />
              </div>
              {drill?.from === "who" && (
                <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
              )}
            </>
          )}

          <Ideas month={s.month} person={who} />

          <h2 className="mt-10 font-display text-2xl font-bold">Spending over time</h2>
          <div className="mt-3 rounded-2xl bg-surface p-4 md:p-6">
            <SpendingChart month={s.month} person={who} onSelect={(m) => s.months.includes(m) && go(m)} />
          </div>
        </>
      )}
    </section>
  );
}
