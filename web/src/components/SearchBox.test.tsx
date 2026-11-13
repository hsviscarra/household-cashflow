import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import SearchBox, { hits } from "./SearchBox";

function Where() {
  const l = useLocation();
  return <p data-testid="where">{l.pathname + l.search}</p>;
}

describe("SearchBox", () => {
  it("finds pages and actions, and turns text or an amount into a search of the lines", () => {
    expect(hits("").map((h) => h.label)).toContain("Upload a statement");
    expect(hits("net worth").map((h) => h.to)).toContain("/debt");
    expect(hits("supermaxi").at(-1)).toEqual({
      label: "Lines with “supermaxi”",
      hint: "Transactions, last 12 months",
      to: "/transactions?months=12&q=supermaxi",
    });
    expect(hits("45.5").at(-1)!.to).toBe("/transactions?months=12&min=45.5&max=45.5");
    expect(hits("a").length).toBeLessThanOrEqual(8);
  });

  it("opens on Ctrl+K, moves with the arrows and goes on Enter", () => {
    render(
      <MemoryRouter>
        <SearchBox />
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const box = screen.getByRole("combobox", { name: "Search pages, actions and lines" });
    expect(box).toHaveFocus();
    fireEvent.change(box, { target: { value: "income tax" } });
    expect(screen.getAllByRole("option")[0]).toHaveTextContent("Income tax");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(screen.getByTestId("where")).toHaveTextContent("/taxes/income");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Search/ }));
    const again = screen.getByRole("combobox");
    fireEvent.change(again, { target: { value: "uber eats" } });
    fireEvent.keyDown(again, { key: "ArrowDown" });
    fireEvent.keyDown(again, { key: "ArrowUp" });
    fireEvent.keyDown(again, { key: "Enter" });
    expect(screen.getByTestId("where")).toHaveTextContent("/transactions?months=12&q=uber%20eats");
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
