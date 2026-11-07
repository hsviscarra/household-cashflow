import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Goal } from "../api";
import GoalsPage, { paceLine } from "./Goals";

const goal = (over: Partial<Goal>): Goal => ({
  goal_id: 1,
  name: "Emergency fund",
  target_amount: "9000",
  target_date: "2027-10-31",
  item_key: "holding-4",
  place_name: "Fondo emergencia",
  saved_amount: null,
  monthly_amount: "400",
  is_active: true,
  notes: null,
  current: "3000",
  as_of: "2026-10-31",
  share: "0.3333",
  left: "6000",
  months_left: 12,
  needed_monthly: "500",
  projected: "7800",
  status: "behind",
  ...over,
});

afterEach(() => vi.unstubAllGlobals());

describe("Goals", () => {
  it("shows each goal's pace and adds, changes, pauses and deletes goals", async () => {
    const calls: { method: string; url: string; body?: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        calls.push({ method, url, body: init?.body as string | undefined });
        const json = (b: unknown, status = 200) =>
          Promise.resolve(new Response(JSON.stringify(b), { status }));
        if (method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
        if (method !== "GET") return json(goal({}), method === "POST" ? 201 : 200);
        return json({
          goals: [
            goal({}),
            goal({
              goal_id: 2,
              name: "Galápagos",
              item_key: null,
              place_name: null,
              saved_amount: "600",
              target_date: null,
              status: "open",
              left: "1900",
              share: "0.24",
              current: "600",
              target_amount: "2500",
            }),
          ],
          places: [{ key: "holding-4", name: "Fondo emergencia", value: "3000", as_of: "2026-10-31" }],
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <GoalsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const fund = await screen.findByRole("region", { name: "Emergency fund" });
    expect(fund).toHaveTextContent("In Fondo emergencia · by Oct 2027");
    expect(fund).toHaveTextContent("Behind");
    expect(fund).toHaveTextContent("3,000.00 of 9,000.00");
    expect(fund).toHaveTextContent("Put 500.00 a month (not 400.00) to reach it by Oct 2027.");
    expect(screen.getByRole("region", { name: "Galápagos" })).toHaveTextContent("Saved amount typed by hand");

    fireEvent.click(screen.getByRole("button", { name: "Add a goal" }));
    const form = screen.getByRole("form", { name: "New goal" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Car" } });
    fireEvent.change(within(form).getByLabelText("Target"), { target: { value: "12000" } });
    fireEvent.change(within(form).getByLabelText("Saved so far"), { target: { value: "1500" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add the goal" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(JSON.parse(calls.find((c) => c.method === "POST")!.body!)).toEqual({
      name: "Car",
      target_amount: "12000",
      target_date: null,
      item_key: null,
      saved_amount: "1500",
      monthly_amount: null,
    });

    fireEvent.click(within(fund).getByRole("button", { name: "Change" }));
    const edit = within(fund).getByRole("form", { name: "Change Emergency fund" });
    expect(within(edit).queryByLabelText("Saved so far")).toBeNull(); // linked: the balance counts
    fireEvent.change(within(edit).getByLabelText("Planned each month (optional)"), {
      target: { value: "500" },
    });
    fireEvent.click(within(edit).getByRole("button", { name: "Save" }));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "PATCH" && c.url === "/api/goals/1")).toBe(true),
    );
    expect(JSON.parse(calls.find((c) => c.method === "PATCH")!.body!).monthly_amount).toBe("500");

    fireEvent.click(within(fund).getByRole("button", { name: "Change" }));
    fireEvent.click(within(fund).getByRole("button", { name: "Pause" }));
    await vi.waitFor(() => expect(calls.some((c) => c.body === '{"is_active":false}')).toBe(true));
    fireEvent.click(within(fund).getByRole("button", { name: "Change" }));
    fireEvent.click(within(fund).getByRole("button", { name: "Delete" }));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/goals/1")).toBe(true),
    );
  });

  it("says what each status needs", () => {
    expect(paceLine(goal({ status: "reached" }))).toBe("Reached. Well done.");
    expect(paceLine(goal({ status: "open" }))).toBe(
      "6,000.00 to go. Add a date to see what it needs each month.",
    );
    expect(paceLine(goal({ status: "late" }))).toBe(
      "6,000.00 short and the date has passed: set a new date.",
    );
    expect(paceLine(goal({ status: "on_pace", monthly_amount: "500" }))).toBe(
      "On pace: 500.00 a month reaches it by Oct 2027.",
    );
    expect(paceLine(goal({ monthly_amount: null }))).toBe("Needs 500.00 a month to reach it by Oct 2027.");
  });
});
