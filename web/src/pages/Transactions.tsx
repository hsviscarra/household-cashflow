import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { fetchTransactions } from "../api";
import { money, monthLong, num, showAmount } from "../money";

const SOURCE_LABEL: Record<string, string> = {
  statement: "Statement",
  excel_history: "Excel history",
  manual: "Manual",
};

function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function TransactionsPage() {
  const [params, setParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : thisMonth();
  const { data, error } = useQuery({
    queryKey: ["transactions", month],
    queryFn: () => fetchTransactions(`${month}-01`),
  });

  const out = (data ?? []).filter((t) => num(t.amount) < 0 && t.type !== "transfer");
  const totalOut = out.reduce((s, t) => s - num(t.amount), 0);

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">Transactions</h1>
      <p className="mt-2 text-lg text-muted">
        Every loaded line for a month. Editing categories arrives with classification (F9).
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-4">
        <label>
          <span className="label">Month</span>
          <input
            type="month"
            className="field w-48"
            value={month}
            onChange={(e) => e.target.value && setParams({ month: e.target.value })}
          />
        </label>
        {data && (
          <p className="pb-2 text-muted">
            {monthLong(`${month}-01`)}: {data.length} lines, <span className="num">{money(totalOut)}</span>{" "}
            out (card payments and transfers excluded)
          </p>
        )}
      </div>

      {error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the transactions: {(error as Error).message}
        </p>
      )}
      {data?.some((t) => t.source === "excel_history") && data.some((t) => t.source === "statement") && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">
          {monthLong(`${month}-01`)} is covered by the Excel history, so the totals on the Overview use the
          workbook. The statement lines below are kept for reference and don’t count twice.
        </p>
      )}
      {data && !data.length && (
        <p className="mt-6 rounded-2xl bg-info-bg px-4 py-3">
          Nothing loaded for {monthLong(`${month}-01`)} yet. Upload and approve a statement on the Import
          page.
        </p>
      )}
      {data && data.length > 0 && (
        <ul
          className="mt-6 divide-y divide-line rounded-2xl border border-line md:hidden"
          aria-label="Transactions (list)"
        >
          {data.map((t) => (
            <li key={t.transaction_id} className="px-4 py-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-semibold">{t.description}</span>
                <span className="num shrink-0">{showAmount(t.amount)}</span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
                <span className="num">
                  {new Date(`${t.txn_date}T00:00:00`).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })}
                </span>
                <span>· {t.account_name ?? SOURCE_LABEL[t.source] ?? t.source}</span>
                {t.person && <span>· {t.person}</span>}
                <span>·</span>
                {t.category_path ?? (
                  <span className="pill bg-attention-bg text-attention-ink">Needs a category</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {data && data.length > 0 && (
        <div className="mt-6 hidden overflow-x-auto rounded-2xl border border-line md:block">
          <table className="w-full text-sm">
            <caption className="sr-only">Transactions in {monthLong(`${month}-01`)}</caption>
            <thead className="bg-surface text-muted">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Date
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Description
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Account
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Who
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Category
                </th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">
                  Amount
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((t) => (
                <tr key={t.transaction_id}>
                  <td className="num whitespace-nowrap px-4 py-2">
                    {new Date(`${t.txn_date}T00:00:00`).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </td>
                  <td className="px-4 py-2">{t.description}</td>
                  <td className="px-4 py-2 text-muted">
                    {t.account_name ?? SOURCE_LABEL[t.source] ?? t.source}
                  </td>
                  <td className="px-4 py-2">{t.person}</td>
                  <td className="px-4 py-2">
                    {t.category_path ?? (
                      <span className="pill bg-attention-bg text-attention-ink">Needs a category</span>
                    )}
                  </td>
                  <td className="num px-4 py-2 text-right">{showAmount(t.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
