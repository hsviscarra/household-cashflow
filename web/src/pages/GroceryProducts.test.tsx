import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GroceryProducts as Data } from "../api";
import GroceryProducts from "./GroceryProducts";

const P = (key: string, type: string | null, brand: string | null, amount: string) => ({
  product_key: key,
  description: key,
  product_group: "Dairy & Eggs",
  product_type: type,
  brand,
  label_source: "claude" as const,
  times: 2,
  quantity: "2",
  amount,
  unit_price: "1.00",
  stores: ["CORPORACION FAVORITA C.A."],
});
const DATA: Data = {
  start: "2026-10-01",
  months: 1,
  total: "30.00",
  products: [P("QSO MOZZ KIOSKO", "Cheese", "Kiosko", "20.00"), P("YOG TONI", "Yogurt", "Toni", "10.00")],
  by_group: [{ name: "Dairy & Eggs", amount: "30.00", products: 2 }],
  by_type: [
    { name: "Cheese", amount: "20.00", products: 1 },
    { name: "Yogurt", amount: "10.00", products: 1 },
  ],
  by_brand: [
    { name: "Kiosko", amount: "20.00", products: 1 },
    { name: "Toni", amount: "10.00", products: 1 },
  ],
  unlabeled: 1,
};

let calls: { method: string; url: string; body: unknown }[];
beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d), { status: 200 }));
      if (url.startsWith("/api/spending/groceries/label")) return json({ labeled: 1 });
      if (method === "PUT") return json({ lines: 2 });
      return json(DATA);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("Grocery products", () => {
  it("labels new products, totals by type or brand, filters and saves a correction", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <GroceryProducts month="2026-10" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText("Every product");
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.url).toContain("start=2026-10-01");

    const totals = screen.getByRole("region", { name: "Where it goes" });
    fireEvent.click(within(totals).getByRole("radio", { name: "By brand" }));
    fireEvent.click(within(totals).getByRole("button", { name: /Toni/ }));
    const list = screen.getByRole("region", { name: /Brand: Toni/ });
    expect(within(list).queryByText("QSO MOZZ KIOSKO")).not.toBeInTheDocument();

    fireEvent.click(within(list).getByRole("button", { name: "Edit YOG TONI" }));
    fireEvent.change(within(list).getByLabelText("Brand"), { target: { value: "Toni Light" } });
    fireEvent.click(within(list).getByRole("button", { name: "Save for every purchase" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual({
      product_key: "YOG TONI",
      product_group: "Dairy & Eggs",
      product_type: "Yogurt",
      brand: "Toni Light",
    });

    fireEvent.click(screen.getByRole("radio", { name: "3 months" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("start=2026-08-01"))).toBe(true));
  });
});
