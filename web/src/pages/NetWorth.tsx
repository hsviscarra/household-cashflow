import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchBalanceSheet, type HoldingClass, type SheetItem } from "../api";
import { money, monthLong, num } from "../money";
import { type Notify, today, day, sheetHeadline, freshness, monthlyDebt } from "./networth/shared";
import { HoldingForm } from "./networth/HoldingForm";
import { Side } from "./networth/ItemCard";
import { Trend, Tile } from "./networth/Trend";

export { CLASSES, sheetHeadline, freshness, maybeDuplicate, monthlyDebt, whatIf } from "./networth/shared";

/** Net worth in two pages (ADR-090): the overview reads (totals, what you own and owe at a glance,
 * the trend); manage edits (values, items, loan tables). */
export default function BalanceSheetSection({ mode = "overview" }: { mode?: "overview" | "manage" }) {
  const q = useQuery({ queryKey: ["networth"], queryFn: fetchBalanceSheet });
  const [params] = useSearchParams();
  const manage = mode === "manage";
  const [adding, setAdding] = useState(false);
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });
  const s = q.data;
  const on = today();
  const [onlyStale, setOnlyStale] = useState(manage && params.get("stale") === "1");
  const allActive = s?.items.filter((i) => i.is_active) ?? [];
  const stale = allActive.filter((i) => freshness(i, on).stale);
  const active = onlyStale ? stale : allActive;
  const paused = s?.items.filter((i) => !i.is_active) ?? [];
  const sum = (f: (i: SheetItem) => boolean) => allActive.filter(f).reduce((t, i) => t + num(i.value), 0);
  const assets = num(s?.assets);
  const share = (cls: HoldingClass[]) =>
    assets ? Math.round((sum((i) => i.side === "asset" && cls.includes(i.holding_class)) / assets) * 100) : 0;
  const loans = allActive.filter((i) => i.loan?.schedule);
  const interestLeft = loans.reduce((t, i) => t + num(i.loan!.schedule!.interest_left), 0);
  const lastPayoff = loans
    .map((i) => i.loan!.schedule!.payoff)
    .filter((x): x is string => !!x)
    .sort()
    .at(-1);
  const biggest = allActive
    .filter((i) => i.side === "liability")
    .sort((a, b) => num(b.value) - num(a.value))[0];

  return (
    <section aria-label="Balance sheet">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto font-display text-4xl font-bold leading-tight">
          {manage ? "Manage what you own and owe" : s ? sheetHeadline(s) : "Debt & Net Worth"}
        </h1>
        {s && stale.length > 0 && manage && (
          <button
            type="button"
            className="btn btn-secondary"
            aria-pressed={onlyStale}
            onClick={() => setOnlyStale(!onlyStale)}
          >
            {onlyStale ? "Show everything" : `Update values (${stale.length} out of date)`}
          </button>
        )}
        {s && stale.length > 0 && !manage && (
          <Link className="btn btn-secondary" to="/debt/manage?stale=1">
            Update values ({stale.length} out of date)
          </Link>
        )}
      </div>
      <p className="mt-2 text-lg text-muted">
        {manage
          ? "Update a value, add or pause an item, load a loan’s table. The totals and the trend are on Overview."
          : "What you own and owe today: property, vehicles, investments, bank balances and the new house’s down payment; loans, credit cards and money owed to people."}
      </p>
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the balance sheet: {(q.error as Error).message}
        </p>
      )}
      {!s && !q.error && <p className="mt-6 text-muted">Adding up what you own and owe…</p>}
      <p
        aria-live="polite"
        className={
          status
            ? `mt-4 rounded-2xl px-4 py-3 ${status.tone === "good" ? "bg-good-bg text-good-ink" : "bg-danger-bg text-danger-ink"}`
            : "sr-only"
        }
      >
        {status?.message ?? ""}
      </p>
      {s && (
        <>
          {!manage && (
            <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
              <Tile
                label="Net worth"
                value={`${num(s.net_worth) < 0 ? "−" : ""}${money(Math.abs(num(s.net_worth)))}`}
                hint={`as of ${day(s.as_of)}`}
              />
              <Tile
                label="You own"
                value={money(s.assets)}
                hint={`property ${share(["property", "vehicle"])}% · cash ${share(["cash"])}% · investments ${share(["investment"])}%`}
              />
              <Tile
                label="You owe"
                value={money(s.liabilities)}
                hint={
                  biggest && num(s.liabilities)
                    ? `${biggest.name} ${Math.round((num(biggest.value) / num(s.liabilities)) * 100)}% of it`
                    : undefined
                }
              />
              <Tile
                label="Debt payments a month"
                value={money(monthlyDebt(s.items))}
                hint="loans and installments"
              />
              {loans.length > 0 ? (
                <Tile
                  label="Interest left on loans"
                  value={money(interestLeft)}
                  hint={lastPayoff ? `last one paid off ${monthLong(lastPayoff)}` : undefined}
                />
              ) : (
                <Tile label="Still to pay on purchases" value={money(s.commitments)} hint="not counted yet" />
              )}
            </dl>
          )}
          {onlyStale && (
            <p className="mt-4 rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink">
              Showing the {stale.length} {stale.length === 1 ? "value" : "values"} out of date: bank and card
              balances older than 45 days, investments older than 10, property older than a year. Update each,
              or pause one that’s counted twice.
            </p>
          )}
          {manage && (
            <div className="mt-4">
              <button className="btn btn-primary" onClick={() => setAdding(!adding)}>
                {adding ? "Close" : "Add something you own or owe"}
              </button>
            </div>
          )}
          {manage && adding && <HoldingForm onDone={() => setAdding(false)} notify={notify} />}

          <div className="grid gap-x-8 xl:grid-cols-2">
            <Side
              title="What you own"
              items={active.filter((i) => i.side === "asset")}
              all={s.items}
              total={s.assets}
              notify={notify}
              compact={!manage}
            />
            <div>
              <Side
                title="What you owe"
                items={active.filter((i) => i.side === "liability")}
                all={s.items}
                total={s.liabilities}
                notify={notify}
                compact={!manage}
              />
              {num(s.commitments) > 0 && !onlyStale && (
                <div className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">
                  <div className="text-xs font-semibold tracking-wide text-muted uppercase">
                    Coming at delivery
                  </div>
                  <p className="mt-1">
                    <strong className="num">{money(s.commitments)}</strong> still to pay on purchases in
                    progress (installments and what’s financed at delivery). It shows here as a commitment,
                    not yet a debt.
                  </p>
                </div>
              )}
            </div>
          </div>
          {manage && paused.length > 0 && !onlyStale && (
            <Side title="Paused (not counted)" items={paused} all={s.items} notify={notify} />
          )}
          {!manage && (
            <p className="mt-6 text-sm">
              <Link className="font-semibold text-primary underline" to="/debt/manage">
                Update a value, add an item or load a loan’s table
              </Link>
            </p>
          )}
          {!manage && <Trend s={s} />}
        </>
      )}
    </section>
  );
}
