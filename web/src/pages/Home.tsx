import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchFlows, fetchMeasures } from "../api";
import { PersonNote } from "../components/Personalize";
import PinnedViews from "../components/PinnedViews";
import { VIEWS_KEY, savedViews } from "../explore";
import { addMonths, localToday, monthLong } from "../money";
import { personParam, usePerson, useSettings } from "../prefs";
import { useWidgets } from "./home/shared";
import { Safe, Needs, Numbers, MoneyNow, NetWorth } from "./home/MoneyCards";
import { CashFlow12, Investments, Budget } from "./home/FlowCards";
import { DataThrough, Customize, Where, Coming, Goals, InboxCard } from "./home/PlanCards";

export { WIDGETS, useWidgets, comingUp } from "./home/shared";

export default function Home() {
  const [person, , ready] = usePerson();
  const [widgets, setWidgets] = useWidgets();
  const [customizing, setCustomizing] = useState(false);
  const [params, setParams] = useSearchParams();
  const thisMonth = `${localToday().slice(0, 7)}`;
  const ym = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : thisMonth;
  const month = `${ym}-01`;
  const go = (by: number) => {
    const next = addMonths(month, by).slice(0, 7);
    setParams(next === thisMonth ? {} : { month: next }, { replace: true });
  };
  const flows = useQuery({
    queryKey: ["cashflow", "flows", month, person],
    queryFn: () => fetchFlows(month, personParam(person)),
    enabled: ready,
  });
  const measures = useQuery({
    queryKey: ["cashflow", "measures", month, person],
    queryFn: () => fetchMeasures(month, personParam(person)),
    enabled: ready,
  });
  const f = flows.data;
  const m = measures.data;
  const { settings } = useSettings();
  const pinned = savedViews(settings[VIEWS_KEY]).filter((v) => v.pinned);

  const parts: Record<string, ReactNode> = {
    needs: <Needs key="needs" />,
    kpis: m ? <Numbers key="kpis" m={m} /> : null,
    safe: <Safe key="safe" />,
    money: <MoneyNow key="money" />,
    networth: <NetWorth key="networth" />,
    cashflow: m ? <CashFlow12 key="cashflow" m={m} /> : null,
    investments: <Investments key="investments" />,
    budget: <Budget key="budget" month={month} />,
    goals: <Goals key="goals" />,
    coming: <Coming key="coming" />,
    where: f ? <Where key="where" f={f} /> : null,
    inbox: <InboxCard key="inbox" />,
    views: pinned.length ? <PinnedViews key="views" views={pinned} /> : null,
  };
  const wide = new Set(["needs", "kpis"]);

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-secondary px-3"
            aria-label="Month before"
            onClick={() => go(-1)}
          >
            ‹
          </button>
          <h1 className="font-display text-4xl font-bold leading-tight">{monthLong(month)}</h1>
          <button
            type="button"
            className="btn btn-secondary px-3"
            aria-label="Month after"
            disabled={ym >= thisMonth}
            onClick={() => go(1)}
          >
            ›
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <DataThrough />
          <button
            type="button"
            className="btn btn-secondary"
            aria-expanded={customizing}
            onClick={() => setCustomizing(!customizing)}
          >
            {customizing ? "Done" : "Customize"}
          </button>
        </div>
      </div>
      <PersonNote person={person} />
      {customizing && <Customize shown={widgets} onChange={setWidgets} />}
      {(flows.error || measures.error) && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the month: {((flows.error || measures.error) as Error).message}. Reload the page; if
          the database was asleep it wakes up in about a minute.
        </p>
      )}
      {f && !f.months.length && (
        <div className="mt-6 max-w-3xl">
          <h2 className="font-display text-2xl font-bold">No cash flow yet</h2>
          <p className="mt-2 text-lg text-muted">
            Load the Cash Flow workbook to see every month since August 2019; statements add the detail.
          </p>
          <Link to="/import" className="btn btn-primary mt-4">
            Load the Excel history
          </Link>
        </div>
      )}
      <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        {widgets
          .filter((w) => w !== "views" || pinned.length > 0) // nothing pinned: no empty card
          .map((w) => (
            <div key={w} className={wide.has(w) ? "lg:col-span-2" : undefined}>
              {parts[w]}
            </div>
          ))}
      </div>
      {!widgets.length && (
        <p className="mt-6 text-muted">Every widget is hidden. Use Customize to bring some back.</p>
      )}
    </section>
  );
}
