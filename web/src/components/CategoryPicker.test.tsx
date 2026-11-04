import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Category, CategoryGroup } from "../api";
import CategoryPicker, { fold, pickEntries, searchEntries } from "./CategoryPicker";

const cat = (id: number, name: string, extra: Partial<Category> = {}): Category => ({
  category_id: id,
  parent_id: null,
  name,
  kind: "expense",
  color: null,
  is_fixed: false,
  is_active: true,
  sort_order: 0,
  description: null,
  lines: 0,
  rules: 0,
  ...extra,
});
const group = (g: Category, children: Category[]): CategoryGroup => ({
  ...g,
  children: children.map((c) => ({ ...c, parent_id: g.category_id })),
});

const GROUPS: CategoryGroup[] = [
  group(cat(1, "Dining", { color: "#E2583E" }), [
    cat(2, "Food Delivery", { description: "Ready meals delivered: Uber Eats, Rappi.", lines: 4 }),
    cat(3, "Restaurants & Cafés", { description: "Restaurants and cafés in person.", lines: 9 }),
  ]),
  group(cat(4, "Transport", { color: "#3AA7D9" }), [
    cat(5, "Rideshare", { description: "Uber rides, Cabify, taxis.", rules: 2 }),
    cat(6, "Parking", { is_active: false }),
  ]),
  group(cat(7, "Pets"), []),
];

function Harness(props: { start?: number | "" }) {
  const [value, setValue] = useState<number | "">(props.start ?? "");
  return (
    <>
      <CategoryPicker label="Category" value={value} onChange={setValue} groups={GROUPS} />
      <output aria-label="value">{String(value)}</output>
    </>
  );
}

function renderPicker(start?: number | "") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness start={start} />
    </QueryClientProvider>,
  );
}
const box = () => screen.getByRole("combobox", { name: "Category" });
const value = () => screen.getByLabelText("value").textContent;
afterEach(() => vi.unstubAllGlobals());

describe("category search", () => {
  it("ignores case and accents and ranks names first", () => {
    expect(fold("Cafés Alícuota")).toBe("cafes alicuota");
    const entries = pickEntries(GROUPS);
    expect(entries.map((e) => e.path)).not.toContain("Transport / Parking"); // archived
    expect(searchEntries(entries, "cafe").map((e) => e.path)).toEqual(["Dining / Restaurants & Cafés"]);
    // "uber" is only in descriptions: both found; "rid" starts a name, so it comes first.
    expect(searchEntries(entries, "uber").map((e) => e.name)).toEqual(["Food Delivery", "Rideshare"]);
    expect(searchEntries(entries, "dining food")[0].name).toBe("Food Delivery");
    expect(searchEntries(entries, "  ")).toHaveLength(entries.length);
    expect(pickEntries(GROUPS, 6).some((e) => e.name === "Parking")).toBe(true); // kept when chosen
  });
});

describe("CategoryPicker", () => {
  it("lists the most used first, then every category, and picks with the keyboard", () => {
    renderPicker();
    fireEvent.focus(box());
    const list = screen.getByRole("listbox", { name: "Category" });
    expect(within(list).getByText("Most used")).toBeInTheDocument();
    const options = within(list).getAllByRole("option");
    // Most used: Restaurants (9 lines), Food Delivery (4), Rideshare (rules only).
    expect(options.slice(0, 3).map((o) => o.textContent)).toEqual([
      expect.stringContaining("Dining / Restaurants & Cafés"),
      expect.stringContaining("Dining / Food Delivery"),
      expect.stringContaining("Transport / Rideshare"),
    ]);
    // The active option shows what goes there.
    expect(options[0]).toHaveTextContent("Restaurants and cafés in person.");
    fireEvent.keyDown(box(), { key: "ArrowDown" });
    expect(box()).toHaveAttribute("aria-activedescendant", options[1].id);
    expect(options[1]).toHaveTextContent("Ready meals delivered");
    fireEvent.keyDown(box(), { key: "ArrowUp" });
    fireEvent.keyDown(box(), { key: "ArrowUp" }); // wraps to the last item
    expect(box()).toHaveAttribute("aria-activedescendant", options[options.length - 1].id);
    fireEvent.keyDown(box(), { key: "ArrowDown" });
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(value()).toBe("3");
    expect(box()).toHaveValue("Dining / Restaurants & Cafés");
    // Room for the color dot before the text (it overlapped it).
    expect(box().style.paddingLeft).toBe("2rem");
    // Closed, it shows the chosen category's description under the field.
    expect(screen.getByText("Restaurants and cafés in person.")).toBeInTheDocument();
  });

  it("searches as you type and picks with a click; Escape keeps the choice", () => {
    renderPicker(5);
    expect(box()).toHaveValue("Transport / Rideshare");
    fireEvent.focus(box());
    fireEvent.change(box(), { target: { value: "deliv" } });
    const list = screen.getByRole("listbox");
    const options = within(list).getAllByRole("option");
    expect(options[0]).toHaveTextContent("Dining / Food Delivery");
    expect(options[0]).toHaveTextContent("Ready meals delivered");
    fireEvent.change(box(), { target: { value: "zzz" } });
    expect(
      within(screen.getByRole("listbox"))
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["+ Create “zzz” as a subcategory…", "No group fits? Create a group…"]);
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(value()).toBe("5");
    expect(box()).toHaveValue("Transport / Rideshare");
    fireEvent.focus(box());
    fireEvent.change(box(), { target: { value: "pets" } });
    fireEvent.click(within(screen.getByRole("listbox")).getByRole("option", { name: /Pets/ }));
    expect(value()).toBe("7");
  });

  it("creates a subcategory in the group of the best match and uses it", async () => {
    const calls: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body));
        calls.push(body);
        return Promise.resolve(
          new Response(
            JSON.stringify(cat(50, body.name, { parent_id: body.parent_id, description: body.description })),
            {
              status: 201,
            },
          ),
        );
      }),
    );
    renderPicker();
    fireEvent.focus(box());
    fireEvent.change(box(), { target: { value: "Taxi" } });
    // "taxi" is in Rideshare's description: the new one is suggested under Transport.
    fireEvent.click(screen.getByRole("option", { name: "+ Create “Taxi” as a subcategory…" }));
    const panel = screen.getByRole("group", { name: "New subcategory" });
    expect(within(panel).getByLabelText("Name")).toHaveValue("Taxi");
    expect(within(panel).getByLabelText("In the group")).toHaveValue("4");
    fireEvent.change(within(panel).getByLabelText("What goes here (optional)"), {
      target: { value: "Street taxis" },
    });
    fireEvent.keyDown(within(panel).getByLabelText("Name"), { key: "Enter" });
    await waitFor(() => expect(value()).toBe("50"));
    expect(calls).toEqual([{ name: "Taxi", parent_id: 4, description: "Street taxis" }]);
    expect(box()).toHaveValue("Transport / Taxi");
  });

  it("creates a group, one deliberate step further, with its first subcategory", async () => {
    let next = 60;
    const calls: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body));
        calls.push(body);
        return Promise.resolve(new Response(JSON.stringify(cat(next++, body.name, body)), { status: 201 }));
      }),
    );
    renderPicker();
    fireEvent.focus(box());
    fireEvent.change(box(), { target: { value: "Concerts" } });
    fireEvent.click(screen.getByRole("option", { name: "+ Create “Concerts” as a subcategory…" }));
    fireEvent.click(screen.getByRole("button", { name: "No group fits? Create a group…" }));
    const panel = screen.getByRole("group", { name: "New group" });
    expect(panel).toHaveTextContent("Groups shape every report");
    fireEvent.change(within(panel).getByLabelText("Group name"), { target: { value: "Entertainment" } });
    expect(within(panel).getByLabelText("First subcategory (optional)")).toHaveValue("Concerts");
    fireEvent.click(within(panel).getByRole("button", { name: "Create and use" }));
    await waitFor(() => expect(value()).toBe("61"));
    expect(calls).toEqual([
      { name: "Entertainment", kind: "expense", description: null },
      { name: "Concerts", parent_id: 60, description: null },
    ]);
    expect(box()).toHaveValue("Entertainment / Concerts");
  });

  it("creates a bare group and reports a failure; Back returns to the list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "'Pets' already exists there." }), { status: 409 }),
        ),
      ),
    );
    renderPicker();
    fireEvent.focus(box());
    fireEvent.click(screen.getByRole("option", { name: "No group fits? Create a group…" }));
    const panel = screen.getByRole("group", { name: "New group" });
    const create = within(panel).getByRole("button", { name: "Create and use" });
    expect(create).toBeDisabled(); // no name yet
    fireEvent.change(within(panel).getByLabelText("Group name"), { target: { value: "Pets" } });
    fireEvent.click(create);
    expect(await within(panel).findByText("'Pets' already exists there.")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Back to the list" }));
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("a subcategory needs its group", async () => {
    renderPicker();
    fireEvent.focus(box());
    fireEvent.change(box(), { target: { value: "zzz" } });
    fireEvent.keyDown(box(), { key: "Enter" }); // the create option is first when nothing matches
    const panel = screen.getByRole("group", { name: "New subcategory" });
    expect(within(panel).getByLabelText("In the group")).toHaveValue("");
    expect(within(panel).getByRole("button", { name: "Create and use" })).toBeDisabled();
    fireEvent.keyDown(within(panel).getByLabelText("Name"), { key: "Escape" });
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });
});
