import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CategoryGroup, GastosInvoice, GastosPerson, GastosSummary } from "../api";
import { pickCategory } from "../test/pick";
import TaxesPage, { sriWords, guessWords, rebateLine } from "./Taxes";

const cats = (food: string) =>
  [
    ["vivienda", "Vivienda"],
    ["educacion", "Educación, arte y cultura"],
    ["salud", "Health"],
    ["alimentacion", "Food"],
    ["vestimenta", "Vestimenta"],
    ["turismo", "Turismo nacional"],
  ].map(([category, label]) => ({
    category,
    label,
    invoices: category === "alimentacion" ? 3 : 0,
    amount: category === "alimentacion" ? food : "0",
  })) as GastosPerson["by_category"];

const person = (
  name: "Hernan" | "Lauren",
  food: string,
  extra: Partial<GastosPerson> = {},
): GastosPerson => ({
  person: name,
  cargas: 0,
  catastrophic: false,
  cap: "5752.60",
  total: food,
  deductible: food,
  rebate: (Number(food) * 0.18).toFixed(2),
  by_category: cats(food),
  to_classify: 0,
  not_deductible: 0,
  ...extra,
});

const SUMMARY: GastosSummary = {
  year: 2026,
  canasta: "821.80",
  rate: "0.18",
  people: [
    person("Hernan", "1000.00", { to_classify: 2 }),
    person("Lauren", "500.00", { not_deductible: 1 }),
  ],
  unassigned: 1,
  unassigned_amount: "40.00",
  labels: {} as GastosSummary["labels"],
};

const CAT = { kind: "expense", color: null, is_fixed: false, is_active: true, sort_order: 0 } as const;
const GROUPS: CategoryGroup[] = [
  {
    ...CAT,
    category_id: 20,
    parent_id: null,
    name: "Health",
    children: [{ ...CAT, category_id: 21, parent_id: 20, name: "Pharmacy" }],
  },
];

const INVOICE: GastosInvoice = {
  invoice_id: 7,
  issue_date: "2026-04-10",
  issuer_ruc: "1790000000001",
  issuer_name: "FARMACIA DE PRUEBA",
  number: "001-001-000000123",
  subtotal: "12.00",
  total: "13.80",
  person: "Hernan",
  person_source: "paid",
  category: null,
  category_source: null,
  transaction_id: 3,
  paid_as: "Health / Pharmacy",
  category_id: null,
  category_path: null,
};

afterEach(() => vi.unstubAllGlobals());

function renderPage(calls: { method: string; url: string; body?: string }[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body as string | undefined });
      const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b)));
      if (url.startsWith("/api/me/settings")) return json({ user: "h", settings: {} });
      if (url.startsWith("/api/gastos/2026/invoices")) return json([INVOICE]);
      if (url === "/api/invoices/7/gastos")
        return json({ ...INVOICE, category: "salud", category_source: "chosen", category_id: 21 });
      if (url === "/api/categories") return json(GROUPS);
      if (url.startsWith("/api/gastos/2026/profile")) return json({ cap: "7396.20" });
      if (url.startsWith("/api/gastos/")) return json({ ...SUMMARY, year: Number(url.split("/")[3]) });
      return json({});
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <TaxesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Tax deductions", () => {
  it("shows each person's rebate, cap and categories, and lets invoices be sorted out", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-07T12:00:00"));
    const calls: { method: string; url: string; body?: string }[] = [];
    renderPage(calls);
    const hernan = await screen.findByRole("region", { name: "Hernan's tax deductions" });
    expect(hernan).toHaveTextContent("Rebate so far180.00");
    expect(hernan).toHaveTextContent("1,000.00 of 5,752.60");
    expect(hernan).toHaveTextContent("Food31,000.00");
    expect(within(hernan).getByRole("link", { name: "Numbers for the annex (CSV)" })).toHaveAttribute(
      "href",
      "/api/gastos/2026/Hernan.csv",
    );
    expect(within(hernan).getByRole("button", { name: "2 invoices need a category" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Lauren's tax deductions" })).toHaveTextContent(
      "1 not deductible",
    );
    expect(screen.getByText(/1 invoice isn't anyone's yet/)).toBeInTheDocument();

    const row = (await screen.findAllByRole("listitem")).find((li) => li.textContent?.includes("FARMACIA"))!;
    expect(row).toHaveTextContent("Apr 10, 2026 · invoice 001-001-000000123 · 12.00 before VAT, 13.80 paid");
    expect(row).toHaveTextContent("whose: from the line that paid it");
    expect(within(row).getByLabelText("All from this supplier")).toBeChecked(); // on by default
    expect(row).toHaveTextContent("No SRI group yet");
    pickCategory(
      await within(row).findByRole("combobox", { name: /Category for FARMACIA/ }),
      "Pharm",
      "Pharmacy",
    );
    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "PUT" && c.url === "/api/invoices/7/gastos")).toBe(true),
    );
    expect(JSON.parse(calls.find((c) => c.url === "/api/invoices/7/gastos")!.body!)).toEqual({
      category_id: 21,
      remember_issuer: true,
    });
    fireEvent.change(within(row).getByLabelText("Whose invoice"), { target: { value: "" } });
    await vi.waitFor(() =>
      expect(calls.filter((c) => c.url === "/api/invoices/7/gastos").map((c) => c.body)).toContain(
        '{"person":null,"remember_issuer":true}',
      ),
    );

    fireEvent.change(within(hernan).getByLabelText("Dependents"), { target: { value: "1" } });
    fireEvent.click(within(hernan).getByRole("button", { name: "Save" }));
    await vi.waitFor(() =>
      expect(calls.find((c) => c.url === "/api/gastos/2026/profile/Hernan")?.body).toBe(
        '{"cargas":1,"catastrophic":false}',
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Not anyone's" }));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.url === "/api/gastos/2026/invoices?person=none")).toBe(true),
    );
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === "/api/gastos/2026/invoices")).toBe(true));
    fireEvent.change(screen.getByLabelText("Tax year"), { target: { value: "2025" } });
    expect(await screen.findByRole("heading", { name: "Tax deductions 2025" })).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("words the guesses and the room left", () => {
    expect(guessWords({ ...INVOICE, category: "salud", category_source: "paid" })).toBe(
      "paid as Health / Pharmacy",
    );
    expect(guessWords({ ...INVOICE, category: "salud", category_source: "products" })).toBe(
      "mostly pharmacy products",
    );
    expect(guessWords({ ...INVOICE, category: "alimentacion", category_source: "products" })).toBe(
      "mostly food",
    );
    expect(guessWords({ ...INVOICE, category: "salud", category_source: "issuer" })).toBe(
      "same as every invoice from this supplier",
    );
    expect(guessWords(INVOICE)).toBeNull();
    expect(sriWords({ category: "salud" })).toBe("Deducts as Health");
    expect(sriWords({ category: "none" })).toBe("Not deductible");
    expect(rebateLine(person("Hernan", "1000.00"), "0.18")).toBe(
      "4,752.60 more in invoices would still count, up to 1,035.47 back.",
    );
    expect(rebateLine(person("Hernan", "5752.60"), "0.18")).toBe(
      "At the cap: more invoices won't raise the rebate.",
    );
    expect(rebateLine(person("Hernan", "10", { cap: null }), "0.18")).toBe(
      "The cap for this year isn't known yet: totals only.",
    );
  });
});
