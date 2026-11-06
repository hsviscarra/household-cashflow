import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Txn } from "../api";
import { PersonSwitch, SavedViewLinks } from "../components/Personalize";
import TransactionsPage, { keep, matches, toCsv, type Filters } from "./Transactions";

const base: Txn = {
  transaction_id: 1,
  txn_date: "2026-10-03",
  post_date: null,
  cash_month: "2026-10-01",
  account_id: 1,
  account_name: "Produbanco Hernan",
  description: "SUPERMAXI QUITO",
  merchant: "SUPERMAXI",
  amount: "-80.00",
  type: "expense",
  category_id: 11,
  category_path: "Groceries › Supermarket",
  person: "Hernan",
  country: "EC",
  source: "statement",
  statement_file_id: 1,
  notes: null,
  category_source: "rule",
  parent_transaction_id: null,
  parts: 0,
};
const TXNS: Txn[] = [
  base,
  {
    ...base,
    transaction_id: 2,
    description: "UBER EATS",
    merchant: "UBER EATS",
    amount: "-20.00",
    category_id: null,
    category_path: null,
    category_source: null,
    person: "Lauren",
    notes: "lunch",
  },
];

let urls: string[];
let settings: Record<string, unknown>;

beforeEach(() => {
  urls = [];
  settings = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/me/settings")) {
        if (init?.method === "PUT") {
          const key = decodeURIComponent(url.split("/").pop()!);
          settings = { ...settings, [key]: JSON.parse(String(init.body)).value };
        }
        return Promise.resolve(new Response(JSON.stringify({ user: "local", settings })));
      }
      urls.push(url);
      if (url.startsWith("/api/transactions")) {
        const person = new URL(url, "http://x").searchParams.get("person");
        return Promise.resolve(
          new Response(JSON.stringify(TXNS.filter((t) => !person || t.person === person))),
        );
      }
      return Promise.resolve(new Response(JSON.stringify([])));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function Where() {
  const { pathname, search } = useLocation();
  return <output aria-label="location">{pathname + search}</output>;
}

function renderAt(path = "/transactions?month=2026-10") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <nav aria-label="Main">
          <PersonSwitch />
          <SavedViewLinks />
        </nav>
        <Where />
        <Routes>
          <Route path="/transactions" element={<TransactionsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("transaction filters", () => {
  it("matches every word against the description, merchant, note and category", () => {
    expect(matches(base, "", false)).toBe(true);
    expect(matches(base, "super groceries", false)).toBe(true);
    expect(matches(base, "super uber", false)).toBe(false);
    expect(matches(TXNS[1], "LUNCH", false)).toBe(true);
    expect(matches(base, "", true)).toBe(false);
    expect(matches(TXNS[1], "", true)).toBe(true);
    expect(matches({ ...TXNS[1], parts: 2 }, "", true)).toBe(false);
  });
});

describe("Transactions page", () => {
  it("searches, filters what needs a category and follows the person switch", async () => {
    renderAt();
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(urls.filter((u) => u.startsWith("/api/transactions"))).toEqual([
      "/api/transactions?month=2026-10-01",
    ]);

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "uber" } });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(screen.getByText(/1 of 2 lines/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "nothing like this" } });
    expect(screen.getByText("No lines match these filters.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "" } });
    fireEvent.click(screen.getByLabelText("Needs a category"));
    expect(screen.getByRole("status", { name: "location" }).textContent ?? "").toContain("todo=1");
    expect(within(screen.getByRole("table")).getByText("UBER EATS")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).queryByText("SUPERMAXI QUITO")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Hernan"));
    await waitFor(() => expect(urls).toContain("/api/transactions?month=2026-10-01&person=Hernan"));
    expect(await screen.findByText("Showing Hernan’s lines only.")).toBeInTheDocument();
    expect(settings.person).toBe("Hernan");
  });

  it("hides columns and changes row size, saved for the person", async () => {
    renderAt();
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Columns & rows"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Account" }));
    await waitFor(() =>
      expect(within(table).queryByRole("columnheader", { name: "Account" })).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Who" }));
    await waitFor(() =>
      expect(within(table).queryByRole("columnheader", { name: "Who" })).not.toBeInTheDocument(),
    );
    expect(within(table).getByRole("columnheader", { name: "Date" })).toBeInTheDocument();
    await waitFor(() =>
      expect(settings["table:transactions"]).toEqual({ columns: ["date", "category", "note"] }),
    );

    fireEvent.click(screen.getByRole("radio", { name: "compact" }));
    await waitFor(() => expect(settings.density).toBe("compact"));
  });

  it("saves a view in the sidebar, opens it with its person and removes it", async () => {
    renderAt("/transactions?month=2026-10&todo=1");
    await screen.findByRole("table");
    fireEvent.click(screen.getByLabelText("Lauren"));
    fireEvent.click(screen.getByRole("button", { name: "Save view" }));
    const form = screen.getByRole("form", { name: "Save this view" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Lauren to sort" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved “Lauren to sort” in the sidebar.")).toBeInTheDocument();
    const sidebar = screen.getByRole("navigation", { name: "Main" });
    const link = await within(sidebar).findByRole("link", { name: "Lauren to sort" });
    expect(link).toHaveAttribute("href", "/transactions?todo=1"); // the month left out
    const views = settings.views as { person: string }[];
    expect(views).toHaveLength(1);
    expect(views[0].person).toBe("Lauren");

    fireEvent.click(screen.getByLabelText("Both"));
    fireEvent.click(link);
    await waitFor(() => expect(settings.person).toBe("Lauren"));
    expect(screen.getByRole("status", { name: "location" }).textContent).toBe("/transactions?todo=1");

    fireEvent.click(screen.getByRole("button", { name: "Remove saved view Lauren to sort" }));
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: "Lauren to sort" })).not.toBeInTheDocument(),
    );
    expect(settings.views).toEqual([]);
  });
});

const NONE: Filters = { q: "", todo: false, account: null, group: null, min: null, max: null, note: false };

describe("ADR-030: filters, tabs, periods, people and CSV", () => {
  it("filters by account, category group, amount, note and amount search", () => {
    expect(keep(base, { ...NONE, account: "Produbanco Hernan" })).toBe(true);
    expect(keep(base, { ...NONE, account: "Capital One" })).toBe(false);
    expect(keep(base, { ...NONE, group: "Groceries" })).toBe(true);
    expect(keep(TXNS[1], { ...NONE, group: "Groceries" })).toBe(false);
    expect(keep(base, { ...NONE, min: 50, max: 100 })).toBe(true);
    expect(keep(base, { ...NONE, min: 81 })).toBe(false);
    expect(keep(base, { ...NONE, max: 79.99 })).toBe(false);
    expect(keep(base, { ...NONE, note: true })).toBe(false);
    expect(keep(TXNS[1], { ...NONE, note: true })).toBe(true);
    expect(keep(base, { ...NONE, q: "$80.00" })).toBe(true);
    expect(keep(base, { ...NONE, q: "81" })).toBe(false);
  });

  it("writes the lines shown as CSV, quoting what needs it", () => {
    const csv = toCsv([{ ...TXNS[1], notes: 'lunch, "work"', counterparty_id: 7 }], new Map([[7, "Rubén"]]));
    const [head, row] = csv.split("\n");
    expect(head).toBe("Date,Posted,Description,Merchant,Account,Who,Category,Note,Person,Country,Amount");
    expect(row).toBe(
      '2026-10-03,,UBER EATS,UBER EATS,Produbanco Hernan,Lauren,,"lunch, ""work""",Rubén,EC,-20.00',
    );
  });

  it("filters on the page, totals what's shown and keeps filters in the address", async () => {
    renderAt();
    const table = await screen.findByRole("table");
    fireEvent.change(screen.getByRole("combobox", { name: "Category" }), { target: { value: "Groceries" } });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(screen.getByText(/1 of 2 lines/)).toBeInTheDocument();
    expect(screen.getByText("Total shown").parentElement).toHaveTextContent("Total shown 80.00");
    expect(screen.getByRole("status", { name: "location" }).textContent).toContain("cat=Groceries");
    fireEvent.change(screen.getByRole("combobox", { name: "Category" }), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "50" } });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "" } });
    fireEvent.click(screen.getByLabelText("Has a note"));
    expect(within(screen.getByRole("table")).getByText("UBER EATS")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).queryByText("SUPERMAXI QUITO")).not.toBeInTheDocument();
  });

  it("asks for 12 months and one person, and links people to their lines", async () => {
    renderAt("/transactions?month=2026-10&months=12&cp=7");
    await screen.findByRole("table");
    expect(urls).toContain("/api/transactions?month=2026-10-01&months=12&limit=2000&counterparty_id=7");
    expect(screen.getAllByText(/November 2025 to October 2026/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Everyone" }));
    expect(screen.getByRole("status", { name: "location" }).textContent).not.toContain("cp=");
  });

  it("shows saved views of this page as tabs", async () => {
    settings = {
      views: [
        { id: "1", name: "Lauren to sort", path: "/transactions", search: "?todo=1", person: "Lauren" },
        { id: "2", name: "Spending", path: "/spending", search: "", person: "Both" },
      ],
    };
    renderAt("/transactions?month=2026-10&todo=1");
    const tabs = await screen.findByRole("navigation", { name: "Saved views" });
    await within(tabs).findByRole("link", { name: "Lauren to sort" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["All", "Lauren to sort"]);
    expect(within(tabs).getByRole("link", { name: "Lauren to sort" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(tabs).getByRole("link", { name: "All" })).toHaveAttribute(
      "href",
      "/transactions?month=2026-10",
    );
    fireEvent.click(within(tabs).getByRole("link", { name: "Lauren to sort" }));
    await waitFor(() => expect(settings.person).toBe("Lauren"));
  });
});
