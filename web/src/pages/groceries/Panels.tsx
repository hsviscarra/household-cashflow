import { type GroceryTrends, type GroceryMover, type GroceryRegular } from "../../api";
import { num, money, monthLong, monthShort } from "../../money";
import { Tile, round, LONG_DAYS, DAYS, signedPct } from "./shared";
import { MonthBars } from "../../components/charts";

export function Kpis({ t, month }: { t: GroceryTrends; month: string }) {
  const withData = t.months.filter((m) => num(m.spent) > 0);
  const avg = withData.length ? withData.reduce((s, m) => s + num(m.spent), 0) / withData.length : 0;
  const high = withData.reduce<(typeof withData)[number] | null>(
    (b, m) => (!b || num(m.spent) > num(b.spent) ? m : b),
    null,
  );
  const low = withData.reduce<(typeof withData)[number] | null>(
    (b, m) => (!b || num(m.spent) < num(b.spent) ? m : b),
    null,
  );
  const tripMonths = t.months.filter((m) => m.trips > 0);
  const trips = tripMonths.length ? tripMonths.reduce((s, m) => s + m.trips, 0) / tripMonths.length : 0;
  const basket =
    tripMonths.length > 0
      ? tripMonths.reduce((s, m) => s + num(m.invoiced), 0) / tripMonths.reduce((s, m) => s + m.trips, 0)
      : 0;
  const now = t.months.find((m) => m.month.slice(0, 7) === month);
  const busiest = t.weekdays.reduce((b, d) => (d.trips > b.trips ? d : b), t.weekdays[0]);
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Tile label="Average month" value={avg ? money(avg) : "—"}>
        {withData.length} months with statements
      </Tile>
      <Tile label="Highest and lowest" value={high ? round(high.spent) : "—"}>
        {high && low
          ? `${monthLong(high.month)} · lowest ${round(low.spent)} in ${monthShort(low.month)}`
          : "No months yet"}
      </Tile>
      <Tile label="Trips a month" value={trips ? trips.toFixed(1) : "—"}>
        {now ? `${now.trips} this month · ` : ""}average basket {money(basket)}
      </Tile>
      <Tile label="Usual shopping day" value={busiest && busiest.trips ? LONG_DAYS[busiest.day] : "—"}>
        {busiest && busiest.trips
          ? `${busiest.trips} of your invoices are from a ${LONG_DAYS[busiest.day]}`
          : "No invoices yet"}
      </Tile>
    </div>
  );
}

export function MonthTable({ t, month }: { t: GroceryTrends; month: string }) {
  return (
    <details>
      <summary className="cursor-pointer text-sm font-semibold text-primary">
        The numbers, month by month
      </summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-muted">
            <tr>
              {["Month", "Spent", "With invoices", "Trips", "Basket", "Top aisle"].map((h, i) => (
                <th
                  key={h}
                  scope="col"
                  className={`px-2 py-1 font-semibold ${i === 0 || i === 5 ? "text-left" : "text-right"}`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {t.months
              .slice()
              .reverse()
              .map((m) => {
                const top = Object.entries(m.aisles).sort((a, b) => num(b[1]) - num(a[1]))[0];
                return (
                  <tr key={m.month} className={m.month.slice(0, 7) === month ? "font-semibold" : ""}>
                    <td className="px-2 py-1.5">{monthLong(m.month)}</td>
                    <td className="num px-2 py-1.5 text-right">{money(m.spent)}</td>
                    <td className="num px-2 py-1.5 text-right">{money(m.invoiced)}</td>
                    <td className="num px-2 py-1.5 text-right">{m.trips}</td>
                    <td className="num px-2 py-1.5 text-right">{m.trips ? money(m.basket) : "—"}</td>
                    <td className="px-2 py-1.5 text-muted">{top ? `${top[0]} · ${money(top[1])}` : "—"}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function Days({ t }: { t: GroceryTrends }) {
  const data = t.weekdays.map((d) => ({
    key: String(d.day),
    label: DAYS[d.day],
    value: num(d.amount),
    selected: true,
    tooltip: (
      <>
        <p className="font-semibold">{LONG_DAYS[d.day]}</p>
        <p className="num">
          {money(d.amount)} · {d.trips} trips
        </p>
      </>
    ),
  }));
  return (
    <section aria-labelledby="days" className="card space-y-3 p-5">
      <div>
        <h2 id="days" className="font-display text-xl font-bold">
          When you shop
        </h2>
        <p className="text-sm text-muted">Invoice amounts by day of the week, over the whole period.</p>
      </div>
      <MonthBars data={data} title="Grocery invoices by day of the week" />
      <table className="sr-only">
        <tbody>
          {t.weekdays.map((d) => (
            <tr key={d.day}>
              <th scope="row">{LONG_DAYS[d.day]}</th>
              <td>{money(d.amount)}</td>
              <td>{d.trips} trips</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function Movers({ title, rows, empty }: { title: string; rows: GroceryMover[]; empty: string }) {
  return (
    <section aria-label={title} className="card space-y-3 p-5">
      <div>
        <h2 className="font-display text-xl font-bold">{title}</h2>
        <p className="text-sm text-muted">
          Unit price the first month you bought it in the period, and the last.
        </p>
      </div>
      {rows.length === 0 && <p className="text-sm text-muted">{empty}</p>}
      <ul className="divide-y divide-line text-sm">
        {rows.map((r) => {
          const ch = num(r.change);
          return (
            <li key={r.product_key} className="flex items-baseline justify-between gap-3 py-2">
              <span className="min-w-0">
                <span className="block truncate" title={r.description}>
                  {r.description}
                </span>
                <span className="num block text-xs text-muted">
                  {money(r.first_price)} in {monthShort(r.first_month)} → {money(r.last_price)} in{" "}
                  {monthShort(r.last_month)}
                </span>
              </span>
              <span className={`num shrink-0 font-semibold ${ch > 0 ? "text-danger-ink" : "text-good-ink"}`}>
                {signedPct(ch)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function Regulars({
  title,
  note,
  rows,
  empty,
  amount,
}: {
  title: string;
  note: string;
  rows: GroceryRegular[];
  empty: string;
  amount: (r: GroceryRegular) => string;
}) {
  return (
    <section aria-label={title} className="card space-y-3 p-5">
      <div>
        <h2 className="font-display text-xl font-bold">{title}</h2>
        <p className="text-sm text-muted">{note}</p>
      </div>
      {rows.length === 0 && <p className="text-sm text-muted">{empty}</p>}
      <ul className="divide-y divide-line text-sm">
        {rows.map((r) => (
          <li key={r.product_key} className="flex items-baseline justify-between gap-3 py-2">
            <span className="min-w-0 truncate" title={r.description}>
              {r.description}
              <span className="block text-xs text-muted">{r.aisle}</span>
            </span>
            <span className="num shrink-0">{amount(r)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
