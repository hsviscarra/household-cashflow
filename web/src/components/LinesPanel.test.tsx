import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CategoryGroup, FlowLine } from "../api";
import { pickCategory } from "../test/pick";
import LinesPanel from "./LinesPanel";

const CAT = { kind: "income", color: null, is_fixed: false, is_active: true, sort_order: 0 } as const;
const GROUPS: CategoryGroup[] = [
  {
    ...CAT,
    category_id: 1,
    parent_id: null,
    name: "Income",
    children: [
      { ...CAT, category_id: 2, parent_id: 1, name: "Salary" },
      { ...CAT, category_id: 3, parent_id: 1, name: "Bonus" },
    ],
  },
];
const LINE: FlowLine = {
  transaction_id: 7,
  txn_date: "2026-10-30",
  description: "TRANSFERENCIA KENILITY",
  merchant: null,
  amount: "4200.0000",
  type: "income",
  category_name: "Salary",
  account_name: "Produbanco",
  person: "Hernan",
  source: "statement",
  notes: null,
  category_id: 2,
  statement_file_id: 9,
  counterparty: null,
  merchant_key: "TRANSFERENCIA KENILITY",
  cash_month: "2026-10-01",
};

let calls: { method: string; url: string; body: unknown }[];
beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
      const json = (d: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(d), { status }));
      if (url.startsWith("/api/cashflow/lines")) return json([LINE]);
      if (url.startsWith("/api/cashflow/search"))
        return json([
          { ...LINE, transaction_id: 8, description: "KENILITY BONUS", category_id: 3, amount: "500.0000" },
        ]);
      if (url === "/api/categories") return json(GROUPS);
      if (url.startsWith("/api/transactions/")) return json({});
      if (url === "/api/merchant-rules") return json({ rule_id: 1 }, 201);
      return json({ detail: "not here" }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderPanel(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <LinesPanel
        target={{
          title: "Salary",
          month: "2026-10-01",
          filter: { category_id: 2, type: "income" },
          moveTo: 2,
        }}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return onClose;
}

describe("LinesPanel", () => {
  it("lists the lines with where they came from and the total", async () => {
    renderPanel();
    const dialog = await screen.findByRole("dialog", { name: "Salary" });
    expect(await within(dialog).findByText("TRANSFERENCIA KENILITY")).toBeInTheDocument();
    expect(within(dialog).getByText(/1 line ·/)).toHaveTextContent("4,200.00");
    expect(within(dialog).getByRole("link", { name: "statement" })).toBeInTheDocument();
    expect(calls[0].url).toContain("category_id=2");
    expect(calls[0].url).toContain("type=income");
  });

  it("changes a category, with a rule when asked", async () => {
    renderPanel();
    await screen.findByText("TRANSFERENCIA KENILITY");
    fireEvent.click(screen.getByLabelText(/make it a rule/));
    pickCategory(
      screen.getByRole("combobox", { name: /Category for TRANSFERENCIA KENILITY/ }),
      "Bon",
      "Bonus",
    );
    expect(await screen.findByText("Changed, and saved a rule for next time.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/transactions/7")!.body).toEqual({ category_id: 3 });
    expect(calls.find((c) => c.url === "/api/merchant-rules")!.body).toMatchObject({
      pattern: "TRANSFERENCIA KENILITY",
      category_id: 3,
    });
  });

  it("moves a line to the month it counts in", async () => {
    renderPanel();
    await screen.findByText("TRANSFERENCIA KENILITY");
    const month = screen.getByRole("combobox", { name: "Month TRANSFERENCIA KENILITY counts in" });
    expect(month).toHaveValue("2026-10-01");
    expect(
      within(month)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["September 2026", "October 2026", "November 2026"]);
    fireEvent.change(month, { target: { value: "2026-11-01" } });
    expect(await screen.findByText("Moved: it counts in November 2026 now.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/transactions/7")!.body).toEqual({ counts_in: "2026-11-01" });
  });

  it("finds a missing line and moves it here; Back and Escape close", async () => {
    const onClose = renderPanel();
    await screen.findByText("TRANSFERENCIA KENILITY");
    fireEvent.change(screen.getByLabelText("Search lines"), { target: { value: "kenility" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    const found = await screen.findByRole("region", { name: "Find a missing line" });
    fireEvent.click(await within(found).findByRole("button", { name: "Move here" }));
    expect(await screen.findByText("Changed.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/transactions/8")!.body).toEqual({ category_id: 2 });
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
