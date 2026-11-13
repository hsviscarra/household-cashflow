import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DataTable, { grouped, sorted, type Column } from "./DataTable";

type Row = { id: number; shop: string; who: string; amount: number };
const ROWS: Row[] = [
  { id: 1, shop: "Bakery", who: "Lauren", amount: 12 },
  { id: 2, shop: "Garage", who: "Hernan", amount: 300 },
  { id: 3, shop: "Cinema", who: "Lauren", amount: 20.5 },
];
const COLUMNS: Column<Row>[] = [
  { id: "shop", label: "Shop", fixed: true, sort: (r) => r.shop, cell: (r) => r.shop },
  { id: "who", label: "Who", sort: (r) => r.who, group: (r) => r.who, cell: (r) => r.who },
  {
    id: "amount",
    label: "Amount",
    align: "right",
    sort: (r) => r.amount,
    total: (r) => r.amount,
    cell: (r) => r.amount.toFixed(2),
  },
  { id: "id", label: "Number", cell: (r) => `#${r.id}` },
];

let saved: { key: string; value: unknown }[];
beforeEach(() => {
  saved = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "PUT")
        saved.push({ key: decodeURIComponent(url.split("/").pop()!), value: JSON.parse(String(init.body)).value });
      return Promise.resolve(new Response(JSON.stringify({ user: "t", settings: {} }), { status: 200 }));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const shops = () =>
  within(screen.getByRole("table"))
    .getAllByRole("row")
    .map((r) => r.textContent ?? "");

function renderTable() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["settings"], { user: "t", settings: {} }); // already loaded: nothing to race
  render(
    <QueryClientProvider client={client}>
      <DataTable
        table="demo"
        caption="Demo"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        defaults={["who", "amount"]}
      />
    </QueryClientProvider>,
  );
}

describe("DataTable", () => {
  it("sorts and groups", () => {
    expect(sorted(ROWS, COLUMNS, { id: "amount", dir: "desc" }).map((r) => r.id)).toEqual([2, 3, 1]);
    expect(sorted(ROWS, COLUMNS, { id: "id", dir: "asc" })).toBe(ROWS); // not a sortable column
    expect(grouped(ROWS, (r) => r.who).map((g) => [g.name, g.rows.length])).toEqual([
      ["Hernan", 1],
      ["Lauren", 2],
    ]);
    expect(grouped(ROWS)).toEqual([{ name: null, rows: ROWS }]);
  });

  it("shows the chosen columns with a totals row, sorts on a click and groups with subtotals", async () => {
    renderTable();
    await screen.findByRole("table", { name: "Demo" });
    expect(shops()).toEqual([
      "ShopWhoAmount",
      "BakeryLauren12.00",
      "GarageHernan300.00",
      "CinemaLauren20.50",
      "Total · 3332.50",
    ]);
    // The layout is a saved setting: it applies a tick after the click.
    fireEvent.click(screen.getByRole("button", { name: "Amount" }));
    await vi.waitFor(() =>
      expect(screen.getByRole("columnheader", { name: /Amount/ })).toHaveAttribute("aria-sort", "ascending"),
    );
    expect(shops().slice(1, 4)).toEqual(["BakeryLauren12.00", "CinemaLauren20.50", "GarageHernan300.00"]);
    fireEvent.click(screen.getByRole("button", { name: /^Amount/ }));
    await vi.waitFor(() => expect(shops()[1]).toBe("GarageHernan300.00"));

    fireEvent.change(screen.getByLabelText("Group by"), { target: { value: "who" } });
    await vi.waitFor(() => expect(shops()).toHaveLength(7));
    expect(shops()).toEqual([
      "ShopWhoAmount ↓",
      "Hernan · 1300.00",
      "GarageHernan300.00",
      "Lauren · 232.50",
      "CinemaLauren20.50",
      "BakeryLauren12.00",
      "Total · 3332.50",
    ]);
    await vi.waitFor(() => expect(saved.at(-1)).toMatchObject({ key: "table:demo" }));
    expect(saved.at(-1)!.value).toEqual({
      columns: ["who", "amount"],
      sort: { id: "amount", dir: "desc" },
      group: "who",
    });
  });

  it("adds, hides and reorders columns", async () => {
    renderTable();
    await screen.findByRole("table", { name: "Demo" });
    fireEvent.click(screen.getByLabelText("Number"));
    await vi.waitFor(() => expect(shops()[0]).toBe("ShopWhoAmountNumber"));
    fireEvent.click(screen.getByRole("button", { name: "Move Number left" }));
    await vi.waitFor(() => expect(shops()[0]).toBe("ShopWhoNumberAmount"));
    expect(screen.getByRole("button", { name: "Move Who left" })).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Who"));
    await vi.waitFor(() => expect(shops()[1]).toBe("Bakery#112.00"));
    expect(screen.queryByLabelText("Shop")).not.toBeInTheDocument(); // fixed: always shown
  });
});
