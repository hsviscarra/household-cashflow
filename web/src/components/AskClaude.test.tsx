import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AskUsage } from "../api";
import AskClaude, { starters, usageLine } from "./AskClaude";

const USAGE: AskUsage = {
  available: true,
  month: "2026-11-01",
  spent: "0.004",
  questions: 4,
  cap: "10",
  left: "9.996",
};

let calls: { method: string; url: string; body: unknown }[];
let usage: AskUsage;
let fail: string | null;
beforeEach(() => {
  calls = [];
  usage = USAGE;
  fail = null;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      calls.push({ method, url, body });
      const json = (d: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(d), { status }));
      if (url === "/api/ask/usage") return json(usage);
      if (url === "/api/ask/cap") return json({ ...usage, cap: body.cap, left: body.cap });
      if (fail) return json({ detail: fail }, 429);
      return json({
        answer: "October cost $4,200.00, $300.00 more than September.",
        cost: "0.03",
        tools_used: ["cash_flow", "cash_flow", "compare_months"],
        usage: { ...usage, spent: "0.034", questions: 5 },
      });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderAt(path: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AskClaude />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Ask Claude", () => {
  it("says what was used and offers questions that fit the page", () => {
    expect(usageLine(USAGE)).toBe("under $0.01 of $10.00 used this month · 4 questions");
    expect(usageLine({ ...USAGE, spent: "1.239", questions: 1 })).toBe(
      "$1.24 of $10.00 used this month · 1 question",
    );
    expect(starters("/spending")[0]).toBe("Explain the numbers on Spending.");
    expect(starters("/")[0]).toBe("How is this month going so far?");
  });

  it("asks with the page and its month, shows the answer and what it cost", async () => {
    renderAt("/spending?month=2026-10");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ask Claude" }));
    const panel = screen.getByRole("dialog", { name: "Ask Claude" });
    expect(await within(panel).findByLabelText("Used this month")).toHaveTextContent("4 questions");

    fireEvent.change(within(panel).getByLabelText("Your question"), {
      target: { value: "Why was October higher?" },
    });
    fireEvent.click(within(panel).getByLabelText("Think harder (costs more)"));
    fireEvent.click(within(panel).getByRole("button", { name: "Ask" }));
    expect(await within(panel).findByText(/October cost \$4,200.00/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")).toEqual({
      method: "POST",
      url: "/api/ask",
      body: { question: "Why was October higher?", page: "/spending", month: "2026-10", deep: true },
    });
    expect(panel).toHaveTextContent("Looked at: cash_flow, compare_months · $0.03");
    expect(within(panel).getByLabelText("Used this month")).toHaveTextContent("5 questions");

    // The limit is yours to change.
    fireEvent.click(within(panel).getByRole("button", { name: "Change the limit" }));
    fireEvent.change(within(panel).getByLabelText("Monthly limit in dollars"), { target: { value: "5" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ cap: "5.00" }));
    await waitFor(() =>
      expect(within(panel).getByLabelText("Used this month")).toHaveTextContent("of $5.00"),
    );
  });

  it("starts from a suggestion, and says so when the limit is used up or Claude isn't set up", async () => {
    fail = "This month's limit for Claude ($10.00) is used up.";
    renderAt("/");
    fireEvent.click(screen.getByRole("button", { name: "Ask Claude" }));
    const panel = screen.getByRole("dialog", { name: "Ask Claude" });
    await within(panel).findByLabelText("Used this month");
    fireEvent.click(within(panel).getByRole("button", { name: "How is this month going so far?" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("limit for Claude ($10.00) is used up");
    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is off without an API key", async () => {
    usage = { ...USAGE, available: false };
    renderAt("/");
    fireEvent.click(screen.getByRole("button", { name: "Ask Claude" }));
    expect(await screen.findByText(/isn’t set up for this app yet/)).toBeInTheDocument();
    expect(screen.getByLabelText("Your question")).toBeDisabled();
  });
});
