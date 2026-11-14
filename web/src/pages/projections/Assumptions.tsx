import { type Projection, type ForecastOptions } from "../../api";
import { useState } from "react";
import { day } from "./shared";
import { Link } from "react-router-dom";
import { money } from "../../money";

export function Seg({
  label,
  values,
  value,
  onChange,
}: {
  label: string;
  values: number[];
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <span role="group" aria-label={label} className="inline-flex rounded-lg bg-surface p-0.5 text-sm">
      {values.map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          className={`h-8 rounded-md px-2.5 font-semibold ${value === v ? "bg-ground text-ink" : "text-muted"}`}
          onClick={() => onChange(v)}
        >
          {v}
        </button>
      ))}
    </span>
  );
}

/** How it's calculated, with the choices that change it. */
export function Assumptions({
  p,
  opts,
  setOpts,
}: {
  p: Projection;
  opts: ForecastOptions;
  setOpts: (o: Partial<ForecastOptions>) => void;
}) {
  const [floor, setFloor] = useState(String(opts.floor || ""));
  return (
    <section className="card" aria-labelledby="assume">
      <h2 id="assume" className="font-display text-xl font-bold">
        How it’s calculated
      </h2>
      <dl className="mt-3 divide-y divide-line text-sm">
        <div className="flex flex-wrap justify-between gap-2 py-2">
          <dt>
            <strong>Starts from</strong> each bank account’s latest balance
          </dt>
          <dd className="text-muted">
            {p.cash_as_of ? `oldest from ${day(p.cash_as_of)}` : "no statement yet"}
          </dd>
        </div>
        <div className="flex flex-wrap justify-between gap-2 py-2">
          <dt>
            <strong>Income and bills</strong>: your recurring items, on their day; loans from their
            amortization table; purchase installments while they last
          </dt>
          <dd>
            <Link className="text-primary underline" to="/recurring">
              Edit in Bills
            </Link>
          </dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <dt>
            <strong>Everyday spending</strong>: {money(p.variable_per_month)} a month, the average of the last
          </dt>
          <dd>
            <Seg
              label="Months to average"
              values={[3, 6, 12]}
              value={opts.average_over}
              onChange={(v) => setOpts({ average_over: v })}
            />
          </dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <dt>
            <strong>Seasons</strong>:{" "}
            {!opts.seasons
              ? "every month ahead gets the same average"
              : p.seasons_from === "all"
                ? "everyday spending goes up and down by the share all your spending does through the year (December, the school months), read from past years; no single group has two years of detail yet"
                : p.seasonal_groups
                  ? `${p.seasonal_groups} ${p.seasonal_groups === 1 ? "group follows" : "groups follow"} their own year (school, December, yearly payments); on cards, paid the month after`
                  : "no group shows a pattern yet (it takes two complete years of history)"}
          </dt>
          <dd>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label="Follow the seasons"
                checked={opts.seasons}
                onChange={(e) => setOpts({ seasons: e.target.checked })}
              />
              {opts.seasons ? "yes" : "no"}
            </label>
          </dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <dt>
            <strong>Money held for others</strong> ({money(p.held ?? 0)}) counted as yours
          </dt>
          <dd>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={opts.include_held}
                onChange={(e) => setOpts({ include_held: e.target.checked })}
              />
              {opts.include_held ? "yes" : "no"}
            </label>
          </dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <dt>
            <strong>Floor</strong>: warn when an account goes under
          </dt>
          <dd>
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setOpts({ floor: Math.max(0, Number(floor) || 0) });
              }}
            >
              <label className="sr-only" htmlFor="floor">
                Floor
              </label>
              <input
                id="floor"
                className="field num h-9"
                style={{ width: "7rem" }}
                inputMode="decimal"
                value={floor}
                placeholder="0"
                onChange={(e) => setFloor(e.target.value)}
              />
              <button type="submit" className="btn btn-quiet h-9 px-3">
                Set
              </button>
            </form>
          </dd>
        </div>
      </dl>
    </section>
  );
}
