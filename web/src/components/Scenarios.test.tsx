import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_FORECAST, type ForecastChange, type Projection } from "../api";
import Scenarios, { savedScenarios, withScenario, MAX_SAVED } from "./Scenarios";

const CAR: ForecastChange = { name: "Car", amount: "-400", every: "month", day: 5 };
const BONUS: ForecastChange = { name: "Bonus", amount: "1000", every: "once", on: "2026-12-15" };

const projection = (end: string, low: string): Projection => ({
  today: "2026-10-20",
  start_cash: "2000",
  cash_as_of: "2026-09-30",
  variable_per_month: "300",
  average_months: [],
  months: [
    {
      month: "2026-11-01",
      income: "0",
      fixed: "0",
      variable: "0",
      purchases: "0",
      net: "0",
      end_cash: "2500",
      items: [],
    },
    {
      month: "2026-12-01",
      income: "0",
      fixed: "0",
      variable: "0",
      purchases: "0",
      net: "0",
      end_cash: end,
      items: [],
    },
  ],
  daily: [
    { day: "2026-10-20", balance: "2000" },
    { day: "2026-12-31", balance: end },
  ],
  lowest: { day: "2026-11-14", balance: low },
  next_payday: null,
  alerts: [],
  first_short: Number(low) < 0 ? "2026-11-14" : null,
  end_cash: end,
});

let puts: { key: string; value: unknown }[];
let posts: ForecastChange[][];
beforeEach(() => {
  puts = [];
  posts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b)));
      if (url.startsWith("/api/me/settings")) {
        if (init?.method === "PUT")
          puts.push({
            key: decodeURIComponent(url.split("/").pop()!),
            value: JSON.parse(String(init.body)).value,
          });
        return json({ user: "h", settings: {} });
      }
      if (init?.method === "POST") {
        const changes = JSON.parse(String(init.body)).changes as ForecastChange[];
        posts.push(changes);
        return json(changes[0].name === "Car" ? projection("2200", "-100") : projection("4000", "900"));
      }
      return json(projection("3000", "900"));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderWith(saved: unknown, changes: ForecastChange[] = []) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["settings"], { user: "h", settings: { "forecast:scenarios": saved } });
  const setChanges = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <Scenarios opts={DEFAULT_FORECAST} changes={changes} setChanges={setChanges} />
    </QueryClientProvider>,
  );
  return setChanges;
}

describe("Scenarios", () => {
  it("reads what was saved and replaces a scenario saved again under its name", () => {
    expect(savedScenarios("nonsense")).toEqual([]);
    expect(savedScenarios([{ name: "A", changes: [CAR] }, { name: 3 }, null])).toEqual([
      { name: "A", changes: [CAR] },
    ]);
    const list = withScenario([{ name: "A", changes: [CAR] }], { name: "A", changes: [BONUS] });
    expect(list).toEqual([{ name: "A", changes: [BONUS] }]);
    const many = Array.from({ length: 20 }, (_, i) => ({ name: `S${i}`, changes: [CAR] }));
    expect(withScenario(many, { name: "New", changes: [CAR] })).toHaveLength(MAX_SAVED);
  });

  it("saves the what-ifs under a name, loads and deletes them", async () => {
    const setChanges = renderWith([{ name: "New car", changes: [CAR] }], [BONUS]);
    fireEvent.change(screen.getByLabelText("Save this what-if as"), {
      target: { value: " Bonus year " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save scenario" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({
      key: "forecast:scenarios",
      value: [
        { name: "Bonus year", changes: [BONUS] },
        { name: "New car", changes: [CAR] },
      ],
    });
    const list = screen.getByRole("list", { name: "Saved scenarios" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Load New car" }));
    expect(setChanges).toHaveBeenCalledWith([CAR]);
    fireEvent.click(screen.getByRole("button", { name: "Delete New car" }));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[1].value).toEqual([{ name: "Bonus year", changes: [BONUS] }]);
  });

  it("compares scenarios with the forecast as it is", async () => {
    renderWith([
      { name: "New car", changes: [CAR] },
      { name: "Bonus year", changes: [BONUS] },
    ]);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Compare New car"));
    fireEvent.click(screen.getByLabelText("Compare Bonus year"));
    const table = await screen.findByRole("table", { name: "Scenarios compared" });
    expect(posts).toEqual([[CAR], [BONUS]]);
    const rows = within(table).getAllByRole("row");
    expect(rows[0]).toHaveTextContent("As it isNew carBonus year");
    expect(rows[1]).toHaveTextContent("Lowest cash900.00 on Nov 14−100.00 on Nov 14900.00 on Nov 14");
    expect(rows[2]).toHaveTextContent("First day shortnoneNov 14none");
    expect(rows[4]).toHaveTextContent("Cash at the end of Dec3,000.002,200.004,000.00");
    expect(rows[5]).toHaveTextContent("Difference at the end—−800.00+1,000.00");
    expect(screen.getByRole("img", { name: /As it is, New car, Bonus year/ })).toBeInTheDocument();
  });
});
