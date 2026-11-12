import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MonthClose } from "../api";
import ClosePage from "./Close";

const CLOSE: MonthClose = {
  month: "2026-10-01",
  ready_on: "2026-11-03",
  ready: true,
  closed_at: null,
  closed_by: null,
  missing: [{ kind: "statement", text: "Bank A: no statement for Oct 9–31", link: "/import" }],
  unusual: [{ group: "Dining", amount: "300.00", average: "150.00" }],
  decided: [
    { rule_id: 7, pattern: "STREAMFLIX", category_path: "Subscriptions / Media", lines: 2, is_active: true },
  ],
  invoices: 12,
  has_report: true,
  sri_url: "https://srienlinea.sri.gob.ec",
};

let calls: { method: string; url: string }[];
let state: MonthClose;

beforeEach(() => {
  calls = [];
  state = structuredClone(CLOSE);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url });
      if (url === "/api/close/2026-10" && method === "POST")
        state = { ...state, closed_at: "2026-11-12T10:00:00", closed_by: "hernan@example.com" };
      if (url === "/api/close/2026-10" && method === "DELETE")
        state = { ...state, closed_at: null, closed_by: null };
      if (url === "/api/review/auto/7/undo")
        return Promise.resolve(new Response(JSON.stringify({ lines: 2 }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify(state), { status: 200 }));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/close?month=2026-10"]}>
        <ClosePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Close the month", () => {
  it("shows the exceptions, closes the month and reopens it", async () => {
    renderPage();
    expect(await screen.findByText(/1 thing is still missing/)).toBeInTheDocument();
    const missing = screen.getByRole("region", { name: "Missing" });
    expect(within(missing).getByRole("link", { name: "Upload it" })).toHaveAttribute("href", "/import");
    expect(screen.getByRole("region", { name: "Unusual" })).toHaveTextContent(
      "Dining: 300.00, usually about 150.00",
    );
    const decided = screen.getByRole("region", { name: "Decided by the app" });
    expect(decided).toHaveTextContent("STREAMFLIX → Subscriptions / Media · 2 lines");
    fireEvent.click(within(decided).getByRole("button", { name: "Undo" }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === "/api/review/auto/7/undo")).toBe(true));
    expect(screen.getByRole("link", { name: "SRI en línea" })).toHaveAttribute("href", CLOSE.sri_url);
    expect(screen.getByRole("link", { name: "Read the October report" })).toHaveAttribute(
      "href",
      "/report?month=2026-10",
    );

    fireEvent.click(screen.getByRole("button", { name: "Close October" }));
    expect(
      await screen.findByText(/October was closed on Nov 12, 2026 by hernan@example.com/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reopen October" }));
    expect(await screen.findByRole("button", { name: "Close October" })).toBeEnabled();
  });

  it("waits until the 3rd", async () => {
    state = { ...CLOSE, ready: false, missing: [] };
    renderPage();
    expect(await screen.findByText(/October can be closed from Nov 3, 2026/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close October" })).toBeDisabled();
  });
});
