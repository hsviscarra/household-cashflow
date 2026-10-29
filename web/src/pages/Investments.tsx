import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchPortfolio, uploadFlex, type Portfolio } from "../api";
import { money, num } from "../money";

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
const signedMoney = (v: string | number) =>
  `${num(v) < 0 ? "−" : num(v) > 0 ? "+" : ""}${money(Math.abs(num(v)))}`;
const qty = (v: string) => Number(v).toLocaleString("en-US", { maximumFractionDigits: 4 });

/** "25,350.40 on Oct 28, 2026 (+950.40 since Oct 27, 2026)" */
export function portfolioLine(p: Portfolio): string | null {
  if (p.total == null || !p.as_of) return null;
  let text = `${money(p.total)} on ${day(p.as_of)}`;
  if (p.previous_total != null && p.previous_as_of)
    text += ` (${signedMoney(num(p.total) - num(p.previous_total))} since ${day(p.previous_as_of)})`;
  return text;
}

export default function InvestmentsSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ibkr"], queryFn: fetchPortfolio });
  const upload = useMutation({
    mutationFn: uploadFlex,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ibkr"] });
      qc.invalidateQueries({ queryKey: ["networth"] });
    },
  });
  const p = q.data;

  if (q.error) return <p className="mt-6 text-sm text-danger-ink">Could not load the investments.</p>;
  if (!p) return null;
  const line = portfolioLine(p);
  const total = num(p.total);
  const error = upload.error as Error | null;
  return (
    <section aria-label="Investments" className="mt-10">
      <h2 className="font-display text-3xl font-bold leading-tight">Investments · Interactive Brokers</h2>
      <p className="mt-1 text-muted">
        {line ?? "No portfolio saved yet."} Positions, cash and value from your IBKR account; the total
        counts in net worth above.
      </p>
      {(!line || p.stale) && (
        <p className="mt-3 rounded-2xl bg-info-bg px-4 py-3 text-sm">
          {line ? "This is more than a week old. " : ""}To update it, ask Claude:{" "}
          <q className="font-semibold">Update my IBKR portfolio in the cash flow app.</q> Claude reads your
          Interactive Brokers connector and saves it here.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="btn btn-quiet h-9 cursor-pointer px-4">
          {upload.isPending ? "Reading…" : "Upload Flex report (XML)"}
          <input
            type="file"
            accept=".xml,text/xml,application/xml"
            className="sr-only"
            aria-label="Flex report"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) upload.mutate(f);
            }}
          />
        </label>
        {error && <span className="text-sm text-danger-ink">{error.message}</span>}
      </div>
      {p.positions.length > 0 && (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3">
            <div className="rounded-2xl bg-surface px-4 py-3">
              <dt className="text-sm text-muted">Total</dt>
              <dd className="num mt-1 font-display text-2xl font-bold">{money(p.total)}</dd>
            </div>
            <div className="rounded-2xl bg-surface px-4 py-3">
              <dt className="text-sm text-muted">Cash</dt>
              <dd className="num mt-1 font-display text-2xl font-bold">{money(p.cash)}</dd>
            </div>
            <div className="rounded-2xl bg-surface px-4 py-3">
              <dt className="text-sm text-muted">Unrealized gain</dt>
              <dd className="num mt-1 font-display text-2xl font-bold">
                {signedMoney(p.positions.reduce((s, x) => s + num(x.unrealized), 0))}
              </dd>
            </div>
          </dl>
          <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
            <table className="w-full text-sm">
              <caption className="sr-only">Positions</caption>
              <thead className="bg-surface text-muted">
                <tr>
                  {["Position", "Quantity", "Price", "Value", "Gain", "Share"].map((h, i) => (
                    <th
                      key={h}
                      scope="col"
                      className={`px-3 py-2 font-semibold ${i ? "text-right" : "text-left"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {p.positions.map((x) => (
                  <tr key={`${x.symbol}-${x.asset_class}`}>
                    <th scope="row" className="px-3 py-2 text-left font-normal">
                      <span className="font-semibold">{x.symbol}</span>
                      {x.description && <span className="block text-xs text-muted">{x.description}</span>}
                    </th>
                    <td className="num px-3 py-2 text-right">{qty(x.quantity)}</td>
                    <td className="num px-3 py-2 text-right">
                      {money(x.price)}
                      {x.currency !== "USD" && <span className="text-muted"> {x.currency}</span>}
                    </td>
                    <td className="num px-3 py-2 text-right">{money(x.value)}</td>
                    <td className="num px-3 py-2 text-right">
                      {x.unrealized == null ? "—" : signedMoney(x.unrealized)}
                    </td>
                    <td className="num px-3 py-2 text-right">
                      {total ? `${Math.round((num(x.value) / total) * 100)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
