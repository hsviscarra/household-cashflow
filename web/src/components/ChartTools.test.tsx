import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { onAsk } from "../ask";
import { csvOf } from "../csv";
import ChartTools from "./ChartTools";

describe("ChartTools", () => {
  it("writes CSV with quoted cells", () => {
    expect(
      csvOf([
        ["Month", "Shop"],
        ["2026-10", 'Dining, "out"'],
        ["2026-11", 12.5],
      ]),
    ).toBe('Month,Shop\n2026-10,"Dining, ""out"""\n2026-11,12.5');
  });

  it("changes the period and hands the question to Ask Claude", () => {
    const onChange = vi.fn();
    const heard: string[] = [];
    const stop = onAsk((q) => heard.push(q));
    render(
      <ChartTools
        name="Cash flow"
        period={{ value: "12" as "6" | "12", options: { "6": "6 months", "12": "12 months" }, onChange }}
        csv={{ file: "x.csv", rows: () => [["a"]] }}
        explain="Explain our cash flow."
      />,
    );
    fireEvent.change(screen.getByLabelText("Cash flow: period"), { target: { value: "6" } });
    expect(onChange).toHaveBeenCalledWith("6");
    fireEvent.click(screen.getByRole("button", { name: "Cash flow: explain" }));
    expect(heard).toEqual(["Explain our cash flow."]);
    expect(screen.getByRole("button", { name: "Cash flow: download CSV" })).toBeInTheDocument();
    stop();
    fireEvent.click(screen.getByRole("button", { name: "Cash flow: explain" }));
    expect(heard).toHaveLength(1); // no longer listening
  });
});
