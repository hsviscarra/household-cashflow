import { describe, expect, it } from "vitest";

import { categoryColor } from "./categories";

describe("categoryColor", () => {
  it("returns the token for a known category", () => {
    expect(categoryColor("Groceries")).toBe("var(--color-cat-groceries)");
  });

  it("falls back to muted for a category without a color yet", () => {
    expect(categoryColor("Pets")).toBe("var(--color-muted)");
  });
});
