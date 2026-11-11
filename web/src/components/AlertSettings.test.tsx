import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AlertSettings from "./AlertSettings";

const SETTINGS = {
  kinds: [
    { key: "late", label: "A statement is late", on: true },
    { key: "budget", label: "A budget reached 80% or went over", on: false },
  ],
  now: ["Diners Club Lauren: statement is late. Closed Sep 30."],
};

afterEach(() => vi.unstubAllGlobals());

describe("AlertSettings (ADR-082)", () => {
  it("shows each kind, what matches now, and saves a change", async () => {
    const calls: { method: string; body: string | null }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        calls.push({ method: init?.method ?? "GET", body: (init?.body as string) ?? null });
        return Promise.resolve(new Response(JSON.stringify(SETTINGS)));
      }),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AlertSettings />
      </QueryClientProvider>,
    );
    expect(await screen.findByLabelText("A statement is late")).toBeChecked();
    expect(screen.getByLabelText("A budget reached 80% or went over")).not.toBeChecked();
    expect(screen.getByText("Right now 1 thing matches:")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("A statement is late"));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(JSON.parse(calls.find((c) => c.method === "PUT")!.body!)).toEqual({ off: ["late", "budget"] });
  });
});
