import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import {
  exportUrl,
  fetchExports,
  fetchReport,
  fetchReportMonths,
  generateReport,
  type Finding,
  type MonthlyReport,
  type Tone,
} from "../api";
import { money, monthLong, num, pct } from "../money";

const TONE: Record<Tone, string> = {
  good: "bg-good-bg text-good-ink",
  bad: "bg-attention-bg text-attention-ink",
  neutral: "bg-info-bg",
};
const TONE_LABEL: Record<Tone, string> = { good: "Good news", bad: "Needs attention", neutral: "Note" };

const signedMoney = (v: string | number) =>
  `${num(v) < 0 ? "−" : num(v) > 0 ? "+" : ""}${money(Math.abs(num(v)))}`;

/** "Written by Claude (claude-sonnet-5-5) on Oct 28, 2026, 9:40 PM, for hernan@example.com" */
export function writtenBy(r: MonthlyReport): string {
  const who = r.written_by === "claude" ? `Claude (${r.model})` : "rules (Claude is off)";
  const when = r.generated_at
    ? ` on ${new Date(r.generated_at).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })}`
    : "";
  return `Written by ${who}${when}, for ${r.generated_by}`;
}

export default function ReportPage() {
  const [params, setParams] = useSearchParams();
  const months = useQuery({ queryKey: ["report-months"], queryFn: fetchReportMonths });
  const month = params.get("month") ?? months.data?.months[0]?.slice(0, 7) ?? null;
  const q = useQuery({
    queryKey: ["report", month],
    queryFn: () => fetchReport(month!),
    enabled: month != null,
  });
  const qc = useQueryClient();
  const write = useMutation({
    mutationFn: () => generateReport(month!),
    onSuccess: (r) => qc.setQueryData(["report", month], r),
  });
  const r = q.data;
  const label = month ? monthLong(`${month}-01`) : null;
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {label ? `${label} report` : "Monthly report"}
      </h1>
      <p className="mt-2 text-lg text-muted">
        The month in 3 to 5 findings, from the same numbers as the other pages, and every view to download.
      </p>
      {months.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the months: {(months.error as Error).message}
        </p>
      )}
      {months.data && months.data.months.length === 0 && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">
          Nothing is loaded yet.{" "}
          <Link className="text-primary underline" to="/import">
            Import statements
          </Link>{" "}
          or the Cash Flow workbook first.
        </p>
      )}
      {months.data && month && (
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <label className="text-sm" htmlFor="report-month">
            Month
          </label>
          <select
            id="report-month"
            className="field h-10"
            value={month}
            onChange={(e) => setParams({ month: e.target.value })}
          >
            {(months.data.months.some((m) => m.startsWith(month))
              ? months.data.months
              : [`${month}-01`, ...months.data.months]
            ).map((m) => (
              <option key={m} value={m.slice(0, 7)}>
                {monthLong(m)}
              </option>
            ))}
          </select>
          <button
            className={`btn ${r ? "btn-secondary" : "btn-primary"} h-10 px-4`}
            disabled={write.isPending}
            onClick={() => write.mutate()}
          >
            {write.isPending
              ? "Writing the report…"
              : r
                ? "Regenerate"
                : months.data.claude
                  ? "Write the report with Claude"
                  : "Write the report"}
          </button>
        </div>
      )}
      {write.error && (
        <p className="mt-4 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not write the report: {(write.error as Error).message}
        </p>
      )}
      {q.error && (
        <p className="mt-4 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the report: {(q.error as Error).message}
        </p>
      )}
      {month && q.data === null && !write.isPending && (
        <p className="mt-6 text-muted">
          No report for {label} yet.{" "}
          {months.data?.claude
            ? "Claude writes the findings from the month's totals (no account numbers or names leave the app)."
            : "Claude is off (no API key), so the findings are written by rules."}
        </p>
      )}
      {r && <ReportBody r={r} />}
      {month && <Downloads month={month} />}
    </section>
  );
}

function ReportBody({ r }: { r: MonthlyReport }) {
  const cf = r.facts.cash_flow;
  const now = cf.month;
  const data = r.facts.data;
  return (
    <>
      {r.notice && (
        <p className="mt-4 rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink">{r.notice}</p>
      )}
      {!data.complete && (
        <div className="mt-4 rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink">
          <p className="font-semibold">This month isn't complete yet, so the numbers may still change.</p>
          <ul className="mt-1 list-disc pl-5 text-sm" aria-label="Still open">
            {data.open.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          <Link className="text-sm underline" to="/status">
            See Data Status
          </Link>
        </div>
      )}
      {now && (
        <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Tile label="Income" value={money(now.income)} was={cf.last_month?.income} />
          <Tile label="Spending" value={money(now.expenses)} was={cf.last_month?.expenses} />
          <Tile
            label="Net"
            value={signedMoney(now.net)}
            was={cf.average_3_months?.net}
            wasLabel="3-month average"
          />
          <Tile
            label="Savings rate"
            value={pct(now.savings_rate)}
            was={cf.last_month?.savings_rate}
            percent
          />
        </dl>
      )}
      <h2 className="mt-10 font-display text-2xl font-bold">Findings</h2>
      <ol className="mt-3 grid gap-3" aria-label="Findings">
        {r.findings.map((f, i) => (
          <FindingCard key={i} f={f} />
        ))}
      </ol>
      <p className="mt-2 text-sm text-muted">{writtenBy(r)}.</p>
    </>
  );
}

function FindingCard({ f }: { f: Finding }) {
  return (
    <li className={`rounded-2xl px-4 py-3 ${TONE[f.tone]}`}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-80">{TONE_LABEL[f.tone]}</p>
      <p className="font-semibold">{f.title}</p>
      <p className="mt-1 text-sm">{f.text}</p>
    </li>
  );
}

function Tile({
  label,
  value,
  was,
  wasLabel = "last month",
  percent,
}: {
  label: string;
  value: string;
  was?: string | null;
  wasLabel?: string;
  percent?: boolean;
}) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="num mt-1 font-display text-2xl font-bold">{value}</dd>
      {was != null && (
        <dd className="text-xs text-muted">
          {wasLabel} <span className="num">{percent ? pct(was) : money(was)}</span>
        </dd>
      )}
    </div>
  );
}

function Downloads({ month }: { month: string }) {
  const q = useQuery({ queryKey: ["exports"], queryFn: fetchExports });
  const year = Number(month.slice(0, 4));
  return (
    <>
      <h2 className="mt-10 font-display text-2xl font-bold">Download</h2>
      <p className="mt-1 text-sm text-muted">
        Monthly data for {monthLong(`${month}-01`)}, yearly views for {year}.
      </p>
      {q.error && <p className="mt-2 text-sm text-danger-ink">Could not load the exports.</p>}
      {q.data && (
        <ul className="mt-3 divide-y divide-line rounded-2xl border border-line" aria-label="Downloads">
          {q.data.map((d) => {
            const period = d.by === "month" ? { month } : { year };
            return (
              <li key={d.key} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                <span>
                  {d.title}{" "}
                  <span className="text-sm text-muted">
                    ({d.by === "month" ? monthLong(`${month}-01`) : year})
                  </span>
                </span>
                <span className="flex gap-3 text-sm">
                  <a className="text-primary underline" href={exportUrl(d.key, "csv", period)} download>
                    CSV<span className="sr-only"> of {d.title}</span>
                  </a>
                  <a className="text-primary underline" href={exportUrl(d.key, "xlsx", period)} download>
                    Excel<span className="sr-only"> of {d.title}</span>
                  </a>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
