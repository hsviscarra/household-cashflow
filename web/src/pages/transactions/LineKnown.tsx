import {
  type Txn,
  fetchCategories,
  fetchLineContext,
  linkInvoice,
  statementPageUrl,
  fetchLineSource,
} from "../../api";
import { useInvalidate, shortDay } from "./shared";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { LineDetails } from "../../components/MerchantReview";
import { money } from "../../money";
import { Link } from "react-router-dom";

/** What's known about the line, to decide what it was (ADR-074): the statement, lines of the same
 * amount and their categories, the transfer's other side, the invoice, the rule, the card's
 * purpose. */
export function LineKnown({ t, onCategory }: { t: Txn; onCategory: (id: number) => void }) {
  const invalidate = useInvalidate();
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
  const ctx = useQuery({
    queryKey: ["line-context", t.transaction_id],
    queryFn: () => fetchLineContext(t.transaction_id),
  });
  const [showStatement, setShowStatement] = useState(false);
  const link = useMutation({
    mutationFn: (invoiceId: number) => linkInvoice(t.transaction_id, invoiceId),
    onSuccess: () => {
      ctx.refetch();
      invalidate();
    },
  });
  const byPath = new Map<string, number>(
    groups.flatMap((g) => g.children.map((c) => [`${g.name} / ${c.name}`, c.category_id] as const)),
  );
  const c = ctx.data;
  return (
    <section
      aria-label="What we know about this line"
      className="space-y-3 rounded-xl bg-surface p-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-3">
        <strong>What we know</strong>
        {t.statement_file_id && (
          <a
            className="text-primary underline"
            target="_blank"
            rel="noreferrer"
            href={statementPageUrl(t.statement_file_id, null)}
          >
            Open the statement
          </a>
        )}
        {t.statement_file_id && (
          <button
            type="button"
            className="text-primary underline"
            onClick={() => setShowStatement(!showStatement)}
          >
            {showStatement ? "Hide the statement text" : "Show where it is on the statement"}
          </button>
        )}
      </div>
      {showStatement && (
        <LineDetails id={t.transaction_id} source={{ scope: "loaded", fetch: fetchLineSource }} />
      )}
      {!c && !ctx.error && <p className="text-muted">Looking…</p>}
      {c?.purpose?.unusual && (
        <p className="rounded-lg bg-attention-bg px-2 py-1.5 text-attention-ink">
          This is {c.purpose.account_name}, kept for {c.purpose.for_whom}’s school (
          {c.purpose.usual.join(", ")}), and this doesn’t look like it. Check it.
        </p>
      )}
      {c && c.same_amount.length > 0 && (
        <div>
          <p className="text-muted">Other lines of exactly {money(t.amount)}:</p>
          <ul className="mt-1 space-y-1" aria-label="Lines of the same amount">
            {c.same_amount.map((x) => {
              const cid = x.category_path ? byPath.get(x.category_path) : undefined;
              return (
                <li key={x.transaction_id} className="flex flex-wrap items-center gap-2">
                  <span className="num">{shortDay(x.txn_date)}</span>
                  <span className="text-muted">{x.account_name}</span>
                  <span>→ {x.category_path ?? "no category"}</span>
                  {cid && cid !== t.category_id && (
                    <button
                      type="button"
                      className="btn btn-secondary h-7 px-2 text-xs"
                      onClick={() => onCategory(cid)}
                    >
                      Use this category
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {c && c.transfer_side.length > 0 && (
        <p>
          <span className="text-muted">Other side: </span>
          {c.transfer_side
            .map((x) => `${x.account_name} ${shortDay(x.txn_date)} ${money(x.amount)}`)
            .join("; ")}
        </p>
      )}
      {c && c.transfer_candidates.length > 0 && (
        <div>
          <p className="text-muted">Could be the other side (same amount, within a week):</p>
          <ul className="mt-1 space-y-0.5">
            {c.transfer_candidates.map((x) => (
              <li key={x.transaction_id}>
                {shortDay(x.txn_date)} · {x.account_name} · <span className="num">{money(x.amount)}</span> ·{" "}
                {x.description}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">Pair them on People &amp; transfers.</p>
        </div>
      )}
      {c && c.invoices.length > 0 && (
        <div>
          <p className="text-muted">
            {c.invoices.some((i) => i.linked)
              ? "The invoice it paid:"
              : "Invoices of this amount around its day:"}
          </p>
          <ul className="mt-1 space-y-1">
            {c.invoices.map((i) => (
              <li key={i.invoice_id} className="flex flex-wrap items-center gap-2">
                <span>
                  <strong>{i.issuer_name}</strong> · {shortDay(i.issue_date)} ·{" "}
                  <span className="num">{money(i.total)}</span>
                  {i.products.length > 0 && <span className="text-muted"> · {i.products.join(", ")}</span>}
                </span>
                {i.linked ? (
                  <span className="pill pill-good">Paid by this line</span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary h-7 px-2 text-xs"
                    disabled={link.isPending}
                    onClick={() => link.mutate(i.invoice_id)}
                  >
                    This is the one
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {c?.rule && (
        <p>
          <span className="text-muted">Rule for lines like it: </span>“{c.rule.pattern}”
          {c.rule.amount_min ? ` at ${money(c.rule.amount_min)}` : ""} → {c.rule.category_path ?? "—"}{" "}
          <Link to="/settings#rules" className="text-primary underline">
            Edit rules
          </Link>
        </p>
      )}
      {c &&
        !c.rule &&
        !c.same_amount.length &&
        !c.invoices.length &&
        !c.transfer_candidates.length &&
        !c.purpose?.unusual && <p className="text-muted">Nothing else matches this line yet.</p>}
    </section>
  );
}
