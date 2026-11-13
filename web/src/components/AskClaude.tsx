import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { askClaude, fetchAskUsage, setAskCap, type AskUsage } from "../api";
import { num } from "../money";
import { PAGES } from "../pages";

// Ask Claude inside the app (ADR-100, plan item D1): a panel on every page. The question goes
// with the page you are on and its month; the answer comes from the same read-only tools Claude
// uses over MCP. Each question costs a little; the month has a limit you choose.

type Exchange = { question: string; answer?: string; error?: string; cost?: string; tools?: string[] };

/** "$0.03 of $10.00 used this month · 4 questions" */
export function usageLine(u: AskUsage): string {
  const used = num(u.spent) > 0 && num(u.spent) < 0.01 ? "under $0.01" : `$${num(u.spent).toFixed(2)}`;
  return `${used} of $${num(u.cap).toFixed(2)} used this month · ${u.questions} ${u.questions === 1 ? "question" : "questions"}`;
}

/** Questions that fit the page, to start from. */
export function starters(path: string): string[] {
  const page = PAGES.find((p) => p.path === path)?.label;
  return [
    page && path !== "/" ? `Explain the numbers on ${page}.` : "How is this month going so far?",
    "Why was last month higher or lower than the month before?",
    "What changed most in our spending in the last three months?",
  ];
}

export default function AskClaude() {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [deep, setDeep] = useState(false);
  const [log, setLog] = useState<Exchange[]>([]);
  const [editCap, setEditCap] = useState<string | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const { pathname, search } = useLocation();
  const qc = useQueryClient();
  const usage = useQuery({ queryKey: ["ask", "usage"], queryFn: fetchAskUsage, enabled: open });
  const u = usage.data;
  const month = new URLSearchParams(search).get("month");

  useEffect(() => {
    if (open) box.current?.focus();
  }, [open]);

  const send = useMutation({
    mutationFn: (question: string) =>
      askClaude({
        question,
        page: pathname,
        month: month && /^\d{4}-\d{2}$/.test(month) ? month : undefined,
        deep,
      }),
    onMutate: (question) => setLog((l) => [...l, { question }]),
    onSuccess: (a) => {
      setLog((l) => [
        ...l.slice(0, -1),
        { ...l[l.length - 1], answer: a.answer, cost: a.cost, tools: a.tools_used },
      ]);
      qc.setQueryData(["ask", "usage"], a.usage);
    },
    onError: (e: Error) => {
      setLog((l) => [...l.slice(0, -1), { ...l[l.length - 1], error: e.message }]);
      qc.invalidateQueries({ queryKey: ["ask", "usage"] });
    },
  });
  const cap = useMutation({
    mutationFn: (v: number) => setAskCap(v),
    onSuccess: (next) => {
      qc.setQueryData(["ask", "usage"], next);
      setEditCap(null);
    },
  });
  const submit = (question: string) => {
    const q = question.trim();
    if (!q || send.isPending) return;
    setTyped("");
    send.mutate(q);
  };
  const off = u ? !u.available || num(u.cap) <= 0 || num(u.left) <= 0 : false;

  return (
    <>
      <button
        type="button"
        className="flex h-10 w-full items-center justify-center rounded-[10px] border border-nav-line text-sm font-semibold text-nav-strong hover:bg-nav-well"
        onClick={() => setOpen(true)}
      >
        Ask Claude
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex justify-end"
          role="dialog"
          aria-modal="true"
          aria-label="Ask Claude"
        >
          <button
            aria-label="Close Ask Claude"
            className="absolute inset-0 bg-ink/30"
            onClick={() => setOpen(false)}
          />
          <div className="relative flex h-full w-full max-w-md flex-col border-l border-line bg-ground text-ink shadow-xl">
            <div className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
              <h2 className="font-display text-xl font-bold">Ask Claude</h2>
              <button type="button" className="text-sm text-primary underline" onClick={() => setOpen(false)}>
                Close
              </button>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3" aria-live="polite">
              {u && !u.available && (
                <p className="rounded-xl bg-attention-bg px-3 py-2 text-sm text-attention-ink">
                  Claude isn’t set up for this app yet (no API key).
                </p>
              )}
              {log.length === 0 && (
                <div>
                  <p className="text-sm text-muted">
                    Ask in plain words. Claude reads your cash flow, spending, bills and net worth to answer;
                    it can’t change anything. Your question and those numbers go to the Claude API.
                  </p>
                  <ul className="mt-3 space-y-2" aria-label="Questions to start from">
                    {starters(pathname).map((s) => (
                      <li key={s}>
                        <button
                          type="button"
                          className="w-full rounded-xl border border-line px-3 py-2 text-left text-sm hover:bg-surface"
                          disabled={off || send.isPending}
                          onClick={() => submit(s)}
                        >
                          {s}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {log.map((x, i) => (
                <div key={i} className="space-y-2">
                  <p className="ml-8 rounded-xl bg-info-bg px-3 py-2 text-sm">{x.question}</p>
                  {x.answer && (
                    <div className="mr-4 rounded-xl bg-surface px-3 py-2 text-sm">
                      <p className="whitespace-pre-wrap">{x.answer}</p>
                      <p className="mt-1 text-xs text-muted">
                        {x.tools?.length ? `Looked at: ${[...new Set(x.tools)].join(", ")} · ` : ""}
                        {num(x.cost) < 0.01 ? "under $0.01" : `$${num(x.cost).toFixed(2)}`}
                      </p>
                    </div>
                  )}
                  {x.error && (
                    <p
                      role="alert"
                      className="mr-4 rounded-xl bg-danger-bg px-3 py-2 text-sm text-danger-ink"
                    >
                      {x.error}
                    </p>
                  )}
                  {!x.answer && !x.error && <p className="text-sm text-muted">Looking at your numbers…</p>}
                </div>
              ))}
            </div>
            <form
              className="border-t border-line px-4 py-3"
              onSubmit={(e) => {
                e.preventDefault();
                submit(typed);
              }}
            >
              <label>
                <span className="sr-only">Your question</span>
                <textarea
                  ref={box}
                  className="field h-20 w-full py-2 text-sm"
                  maxLength={1000}
                  placeholder="Why was October higher than September?"
                  value={typed}
                  disabled={off}
                  onChange={(e) => setTyped(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submit(typed);
                    } else if (e.key === "Escape") setOpen(false);
                  }}
                />
              </label>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} />
                  Think harder (costs more)
                </label>
                <button
                  type="submit"
                  className="btn btn-primary h-9 px-4 text-sm"
                  disabled={off || !typed.trim() || send.isPending}
                >
                  Ask
                </button>
              </div>
              {u && (
                <div className="mt-2 text-xs text-muted">
                  <span aria-label="Used this month">{usageLine(u)}</span>
                  {num(u.left) <= 0 && num(u.cap) > 0 && " · the limit is used up until next month"}
                  {num(u.cap) <= 0 && " · turned off"}{" "}
                  {editCap === null ? (
                    <button
                      type="button"
                      className="text-primary underline"
                      onClick={() => setEditCap(String(num(u.cap)))}
                    >
                      Change the limit
                    </button>
                  ) : (
                    <span className="mt-1 flex items-center gap-2">
                      <label className="flex items-center gap-1">
                        Monthly limit, $
                        <input
                          className="field num h-8 !w-20 text-xs"
                          inputMode="decimal"
                          aria-label="Monthly limit in dollars"
                          value={editCap}
                          onChange={(e) => setEditCap(e.target.value)}
                        />
                      </label>
                      <button
                        type="button"
                        className="text-primary underline"
                        disabled={cap.isPending || !Number.isFinite(Number(editCap)) || Number(editCap) < 0}
                        onClick={() => cap.mutate(Number(editCap))}
                      >
                        Save
                      </button>
                      <button type="button" className="underline" onClick={() => setEditCap(null)}>
                        Cancel
                      </button>
                    </span>
                  )}
                  {cap.error && <span role="alert"> {(cap.error as Error).message}</span>}
                </div>
              )}
            </form>
          </div>
        </div>
      )}
    </>
  );
}
