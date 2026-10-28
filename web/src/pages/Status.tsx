import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { BackupPanel } from "../components/BackupPanel";
import { SourcesSection } from "../components/SourcesSection";
import { fetchStatus, type DataStatus, type MonthStatus, type StatusItem } from "../api";
import { monthLong, monthShort } from "../money";

const ACTION: Record<StatusItem["kind"], string> = {
  statement: "Upload",
  import: "Open the import",
  uncategorized: "Review",
  transfer: "Review",
  recurring: "Open the grid",
  balance: "Check the statements",
};

const KIND_LABEL: Record<StatusItem["kind"], string> = {
  statement: "Statement",
  import: "Import",
  uncategorized: "Category",
  transfer: "Transfer",
  recurring: "Recurring",
  balance: "Balance",
};

/** "3 things missing" / "1 thing missing" / "Complete". */
export function summary(m: MonthStatus): string {
  if (m.complete) return "Complete";
  return `${m.items.length} ${m.items.length === 1 ? "thing" : "things"} missing`;
}

export default function StatusPage() {
  const q = useQuery({ queryKey: ["status"], queryFn: fetchStatus });
  const data = q.data;
  const statementMonths = data?.months.filter((m) => m.source === "statements") ?? [];
  const latest = statementMonths[0] ?? data?.months[0];

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {latest ? `${monthLong(latest.month)}: ${summary(latest).toLowerCase()}` : "Data Status"}
      </h1>
      <p className="mt-2 text-lg text-muted">
        Each month is complete when every account’s statements cover it, every import is approved and every
        line has a category; otherwise this lists what is missing.
      </p>
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the data status: {(q.error as Error).message}
        </p>
      )}
      <SourcesSection />
      {!data && !q.error && <p className="mt-6 text-muted">Checking every month…</p>}
      {data && (
        <>
          <ul className="mt-6 space-y-4" aria-label="Months">
            {statementMonths.map((m, i) => (
              <MonthCard key={m.month} m={m} open={i === 0} />
            ))}
          </ul>
          {data.excel_through && (
            <p className="mt-4 rounded-2xl bg-good-bg px-4 py-3 text-good-ink">
              Through {monthLong(data.excel_through)}: complete, from the Cash Flow sheet.
            </p>
          )}
          {statementMonths.length > 0 && <CoverageTable data={data} months={statementMonths} />}
          <LoadLog loads={data.loads} />
          <BackupPanel />
        </>
      )}
    </section>
  );
}

function MonthCard({ m, open }: { m: MonthStatus; open: boolean }) {
  const id = `month-${m.month}`;
  return (
    <li className="rounded-2xl border border-line" aria-labelledby={id}>
      <details open={open} className="group p-4 md:p-5">
        <summary className="flex cursor-pointer list-none flex-wrap items-baseline justify-between gap-2">
          <h2 id={id} className="font-display text-2xl font-bold">
            <span
              aria-hidden
              className="mr-2 inline-block text-muted transition-transform group-open:rotate-90"
            >
              ›
            </span>
            {monthLong(m.month)}
          </h2>
          <span className={`pill ${m.complete ? "pill-good" : "bg-attention-bg text-attention-ink"}`}>
            {summary(m)}
          </span>
        </summary>
        {m.items.length > 0 && (
          <ul className="mt-3 divide-y divide-line">
            {m.items.map((item, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2">
                <span>
                  <span className="mr-2 text-xs font-semibold uppercase tracking-wide text-muted">
                    {KIND_LABEL[item.kind]}
                  </span>
                  {item.text}
                </span>
                <Link className="text-primary underline-offset-2 hover:underline" to={item.link}>
                  {ACTION[item.kind]}
                  <span className="sr-only"> for {item.text}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </details>
    </li>
  );
}

const STATE: Record<"full" | "partial" | "none", { label: string; look: string }> = {
  full: { label: "Full", look: "bg-good-bg text-good-ink" },
  partial: { label: "Part", look: "bg-attention-bg text-attention-ink" },
  none: { label: "None", look: "text-muted" },
};

function CoverageTable({ data, months }: { data: DataStatus; months: MonthStatus[] }) {
  const ordered = [...months].reverse();
  return (
    <div className="mt-8">
      <h2 className="font-display text-2xl font-bold">Statements by account</h2>
      <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
        <table className="w-full text-sm">
          <caption className="sr-only">Statement coverage by account and month</caption>
          <thead className="bg-surface text-muted">
            <tr>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Account
              </th>
              {ordered.map((m) => (
                <th key={m.month} scope="col" className="px-3 py-2 text-center font-semibold">
                  {monthShort(m.month)} {m.month.slice(2, 4)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.accounts.map((a) => (
              <tr key={a.account_id}>
                <th scope="row" className="px-4 py-2 text-left font-medium">
                  {a.name}
                </th>
                {ordered.map((m) => {
                  const c = m.coverage.find((x) => x.account_id === a.account_id);
                  if (!c) return <td key={m.month} />;
                  const s = STATE[c.state];
                  return (
                    <td key={m.month} className="px-2 py-1.5 text-center">
                      <span
                        className={`inline-block min-w-[3.5rem] rounded-full px-2 py-0.5 text-xs font-semibold ${s.look}`}
                        title={`${c.covered_days} of ${c.days} days`}
                      >
                        {s.label}
                        {c.state === "partial" && (
                          <span className="num font-normal">
                            {" "}
                            {c.covered_days}/{c.days}
                          </span>
                        )}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-sm text-muted">
        Full: approved statements cover every day of the month. Part: days covered of the month. Switch off an
        account you don’t track in{" "}
        <Link className="text-primary underline" to="/settings">
          Settings
        </Link>
        .
      </p>
    </div>
  );
}

const SOURCE: Record<string, string> = { statement: "Statement", excel_history: "Cash Flow sheet" };

function LoadLog({ loads }: { loads: DataStatus["loads"] }) {
  return (
    <div className="mt-8">
      <h2 className="font-display text-2xl font-bold">Load log</h2>
      {loads.length === 0 ? (
        <p className="mt-2 text-muted">
          Nothing loaded yet.{" "}
          <Link className="text-primary underline" to="/import">
            Upload statements
          </Link>
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
          <table className="w-full text-sm">
            <caption className="sr-only">Latest loads</caption>
            <thead className="bg-surface text-muted">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  When
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  What
                </th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">
                  Lines
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  By
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {loads.map((l, i) => (
                <tr key={i}>
                  <td className="num whitespace-nowrap px-4 py-2">
                    {new Date(l.loaded_at.endsWith("Z") ? l.loaded_at : `${l.loaded_at}Z`).toLocaleString(
                      "en-US",
                      {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      },
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <span className="text-muted">{SOURCE[l.source] ?? l.source}</span>
                    {l.file_name && <span className="block break-all font-mono text-xs">{l.file_name}</span>}
                  </td>
                  <td className="num px-4 py-2 text-right">{l.rows}</td>
                  <td className="px-4 py-2 text-muted">{l.loaded_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
