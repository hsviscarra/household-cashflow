import { type Bill, type BillStatus } from "../../api";
import { STATUS, isIn, size, DOW, weeks } from "./shared";
import { money, localToday, monthLong, monthShort } from "../../money";

export function Chip({ b }: { b: Bill }) {
  const s = STATUS[b.status];
  return (
    <span
      className={`block truncate rounded-md px-1.5 py-0.5 text-xs font-medium ${isIn(b) ? "bg-info-bg text-ink" : s.cls}`}
      title={`${b.name}: ${money(size(b))}, ${isIn(b) ? "income" : s.label.toLowerCase()}`}
    >
      {isIn(b) ? "↑ " : ""}
      {b.name} <span className="num">{money(size(b))}</span>
      <span className="sr-only">, {isIn(b) ? "money in" : s.label.toLowerCase()}</span>
    </span>
  );
}

export function Calendar({ month, bills }: { month: string; bills: Bill[] }) {
  const today = localToday();
  const days = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0).getDate();
  const on = (d: number) => bills.filter((b) => b.due_day !== null && Math.min(b.due_day, days) === d);
  const noDay = bills.filter((b) => b.due_day === null);
  const sorted = [...bills].sort((a, b) => (a.due_day ?? 99) - (b.due_day ?? 99));
  return (
    <section className="card mt-6" aria-label={`${monthLong(`${month}-01`)} calendar`}>
      <div className="hidden grid-cols-7 gap-1 md:grid" role="table" aria-label="Bills by day">
        <div role="row" className="contents">
          {DOW.map((d) => (
            <div
              key={d}
              role="columnheader"
              className="px-2 pb-1 text-xs font-semibold tracking-wide text-muted uppercase"
            >
              {d}
            </div>
          ))}
        </div>
        {weeks(month).map((week, i) => (
          <div role="row" className="contents" key={i}>
            {week.map((d, j) => {
              const iso = d ? `${month}-${String(d).padStart(2, "0")}` : "";
              return (
                <div
                  key={j}
                  role="cell"
                  className={`min-h-24 rounded-lg border p-1.5 ${d ? "border-line" : "border-transparent"} ${iso === today ? "ring-2 ring-primary" : ""}`}
                >
                  {d && (
                    <>
                      <span className="num text-xs text-muted">{d}</span>
                      <div className="mt-1 space-y-1">
                        {on(d).map((b) => (
                          <Chip key={b.template_id} b={b} />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <ul className="divide-y divide-line md:hidden" aria-label="Bills by day (list)">
        {sorted.map((b) => (
          <li key={b.template_id} className="flex items-center justify-between gap-3 py-2">
            <span>
              <span className="num text-sm text-muted">
                {b.due_day ? `${monthShort(`${month}-01`)} ${b.due_day}` : "No set day"}
              </span>
              <span className="block font-medium">{b.name}</span>
            </span>
            <Chip b={b} />
          </li>
        ))}
      </ul>
      {noDay.length > 0 && (
        <div className="mt-4 hidden md:block">
          <h2 className="text-sm font-semibold text-muted">No set day yet</h2>
          <div className="mt-1 flex flex-wrap gap-2">
            {noDay.map((b) => (
              <Chip key={b.template_id} b={b} />
            ))}
          </div>
          <p className="mt-1 text-xs text-muted">
            The day comes from the lines that paid it; set it on the Year grid when it hasn’t been paid yet.
          </p>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-4 text-xs text-muted">
        {(["paid", "due", "late"] as BillStatus[]).map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <span className={`rounded-md px-1.5 py-0.5 font-medium ${STATUS[s].cls}`}>{STATUS[s].label}</span>
            {s === "paid" ? "a line paid it" : s === "due" ? "expected" : "past its day, not seen"}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="rounded-md bg-info-bg px-1.5 py-0.5 font-medium text-ink">↑ In</span>money coming
          in
        </span>
      </div>
    </section>
  );
}
