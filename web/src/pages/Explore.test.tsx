import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ExploreResult } from "../api";
import PinnedViews from "../components/PinnedViews";
import { DEFAULT_VIEW, exploreCsv, monthsOf, request, savedViews, viewSpec } from "../explore";
import ExplorePage, { viewTitle } from "./Explore";

const R: ExploreResult = {
  measure: "amount",
  rows_by: "group",
  cols_by: "month",
  rows: ["Groceries", "Dining, out"],
  cols: ["2026-10", "2026-11"],
  cells: [
    ["300", "100"],
    ["90", "0"],
  ],
  row_totals: ["400", "90"],
  col_totals: ["390", "100"],
  total: "490",
  folded: 0,
};
const FLAT: ExploreResult = { ...R, cols_by: null, cols: [], cells: [["400"], ["90"]], col_totals: [] };

let urls: string[];
let settings: Record<string, unknown>;
beforeEach(() => {
  urls = [];
  settings = {};
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 10, 13, 12));
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d)));
      if (url.startsWith("/api/me/settings")) {
        if (init?.method === "PUT")
          settings[decodeURIComponent(url.split("/").pop()!)] = JSON.parse(String(init.body)).value;
        return json({ user: "h", settings });
      }
      if (url === "/api/categories")
        return json([{ category_id: 7, name: "Groceries", kind: "expense", children: [] }]);
      urls.push(url);
      return json(url.includes("cols=") ? R : FLAT);
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const wrap = (ui: React.ReactNode, seed?: Record<string, unknown>) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (seed) client.setQueryData(["settings"], { user: "h", settings: seed });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("Explore", () => {
  it("reads a saved view, works out the period and writes the CSV", () => {
    expect(viewSpec({ rows: "person", cols: "person", measure: "x", period: "99" })).toEqual({
      ...DEFAULT_VIEW,
      rows: "person",
      cols: "none", // rows and columns can't be the same
    });
    expect(savedViews([{ name: "A", spec: { rows: "merchant" }, pinned: true }, { spec: {} }, 3])).toEqual([
      { name: "A", spec: { ...DEFAULT_VIEW, rows: "merchant" }, pinned: true },
    ]);
    expect(monthsOf("6", "2026-11-13")).toEqual({ start: "2026-06-01", end: "2026-11-01" });
    expect(monthsOf("ytd", "2026-11-13")).toEqual({ start: "2026-01-01", end: "2026-11-01" });
    expect(monthsOf("last_year", "2026-11-13")).toEqual({ start: "2025-01-01", end: "2025-12-01" });
    expect(request({ ...DEFAULT_VIEW, person: "Lauren", cols: "none", group_id: 7 }, "2026-11-13")).toEqual({
      start: "2026-06-01",
      end: "2026-11-01",
      rows: "group",
      cols: undefined,
      measure: "amount",
      person: "Lauren",
      group_id: 7,
    });
    expect(viewTitle({ ...DEFAULT_VIEW, person: "Lauren" })).toBe(
      "Amount spent by group and month, last 6 months, Lauren",
    );
    expect(exploreCsv(R)).toBe(
      'Group,2026-10,2026-11,Total\nGroceries,300.00,100.00,400.00\n"Dining, out",90.00,0.00,90.00\nTotal,390.00,100.00,490.00',
    );
    expect(exploreCsv({ ...FLAT, measure: "lines" })).toBe(
      'Group,Number of lines\nGroceries,400\n"Dining, out",90\nTotal,490',
    );
  });

  it("builds the view, shows it as a table or a chart, and keeps it by name", async () => {
    wrap(<ExplorePage />);
    const table = await screen.findByRole("table", {
      name: "Amount spent by group and month, last 6 months",
    });
    expect(urls[0]).toBe("/api/explore?start=2026-06-01&end=2026-11-01&rows=group&cols=month&measure=amount");
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Groceries300.00100.00400.00");
    expect(rows[3]).toHaveTextContent("Total390.00100.00490.00");

    fireEvent.change(screen.getByLabelText("Columns"), { target: { value: "none" } });
    await waitFor(() => expect(urls.at(-1)).not.toContain("cols="));
    fireEvent.change(screen.getByLabelText("Only the group"), { target: { value: "7" } });
    await waitFor(() => expect(urls.at(-1)).toContain("group_id=7"));
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "chart" } });
    expect(
      await screen.findByRole("img", { name: /^Amount spent by group, last 6 months/ }),
    ).toBeInTheDocument();
    expect(settings["explore:last"]).toMatchObject({ cols: "none", group_id: 7, show: "chart" });

    fireEvent.change(screen.getByLabelText("Save this view as"), { target: { value: "Groceries only" } });
    fireEvent.click(screen.getByRole("button", { name: "Save view" }));
    const saved = await screen.findByRole("list", { name: "Saved views" });
    fireEvent.click(within(saved).getByLabelText("Pin Groceries only to Home"));
    await waitFor(() =>
      expect(settings["explore:views"]).toEqual([
        { name: "Groceries only", spec: expect.objectContaining({ group_id: 7 }), pinned: true },
      ]),
    );
    fireEvent.click(within(saved).getByRole("button", { name: "Delete Groceries only" }));
    await waitFor(() => expect(settings["explore:views"]).toEqual([]));
  });

  it("shows pinned views on Home with their first rows", async () => {
    wrap(
      <PinnedViews views={[{ name: "By group", spec: { ...DEFAULT_VIEW, cols: "none" }, pinned: true }]} />,
    );
    const card = screen.getByRole("region", { name: "Your views" });
    const table = await within(card).findByRole("table", { name: "By group" });
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Groceries400.00");
    expect(within(card).getByRole("link", { name: "Explore →" })).toHaveAttribute("href", "/explore");
  });
});
