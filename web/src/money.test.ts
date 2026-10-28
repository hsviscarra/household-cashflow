import { describe, expect, it } from "vitest";

import { niceTicks } from "./components/charts";
import { money, monthLong, monthShort, pct, showAmount, signed, short, localToday } from "./money";

describe("money formatting", () => {
  it("formats decimal strings with two decimals and separators", () => {
    expect(money("12345.6")).toBe("12,345.60");
    expect(money(null)).toBe("0.00");
    expect(showAmount("-0.00")).toBe("0.00");
    expect(showAmount("-5")).toBe("5.00");
    expect(showAmount("5")).toBe("+5.00");
    expect(signed("575")).toBe("+575.00");
    expect(signed(-20)).toBe("-20.00");
    expect(short(12500)).toBe("12.5K");
    expect(pct("0.8636")).toBe("86%");
    expect(pct(null)).toBe("—");
  });

  it("names months from ISO dates without time zones", () => {
    expect(monthShort("2026-01-01")).toBe("Jan");
    expect(monthLong("2019-08-01")).toBe("August 2019");
  });
});

describe("niceTicks", () => {
  it("returns clean bounds that cover the data", () => {
    const t = niceTicks(0, 9447.2);
    expect(t[0]).toBe(0);
    expect(t[t.length - 1]).toBeGreaterThanOrEqual(9447.2);
    expect(t.length).toBeLessThanOrEqual(6);
    const neg = niceTicks(-16825, 28089);
    expect(neg[0]).toBeLessThanOrEqual(-16825);
    expect(neg).toContain(0);
    expect(niceTicks(5, 5).length).toBeGreaterThan(1);
  });
});

describe("localToday", () => {
  it("uses the local date, not UTC", () => {
    expect(localToday(new Date(2026, 9, 27, 23, 30))).toBe("2026-10-27");
    expect(localToday(new Date(2027, 0, 5))).toBe("2027-01-05");
  });
});
