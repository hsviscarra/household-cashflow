import { describe, expect, it } from "vitest";

import { layout, squarify } from "./Treemap";

describe("treemap layout", () => {
  it("fills the box, with each block's area in proportion", () => {
    const rects = squarify([6, 6, 4, 3, 2, 2, 1], { x: 0, y: 0, w: 6, h: 4 });
    const area = rects.reduce((s, r) => s + r.w * r.h, 0);
    expect(area).toBeCloseTo(24);
    expect(rects[0].w * rects[0].h).toBeCloseTo(6);
    for (const r of rects) {
      expect(r.x + r.w).toBeLessThanOrEqual(6.0001);
      expect(r.y + r.h).toBeLessThanOrEqual(4.0001);
    }
  });

  it("drops empty items, sorts biggest first and works in percent", () => {
    const blocks = layout([
      { key: "a", label: "A", amount: 10 },
      { key: "b", label: "B", amount: 30 },
      { key: "z", label: "Z", amount: 0 },
      { key: "r", label: "Refunds", amount: -5 },
    ]);
    expect(blocks.map((b) => b.key)).toEqual(["b", "a"]);
    const share = blocks.map((b) => (b.w * b.h) / 100 / 100);
    expect(share[0]).toBeCloseTo(0.75);
    expect(layout([])).toEqual([]);
  });
});
