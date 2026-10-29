import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// A synthetic Flex report (api/tests/unit/test_ibkr.py: flex): 2 positions, 25,350.40 on Oct 28.
const FLEX = fileURLToPath(new URL("./fixtures/sample-flex.xml", import.meta.url));

test("investments: a Flex report becomes positions and a net worth value", async ({ page }) => {
  await page.goto("/debt");
  const section = page.getByRole("region", { name: "Investments" });
  await section.getByLabel("Flex report").setInputFiles(FLEX);
  await expect(section).toContainText("25,350.40 on Oct 28, 2026");
  const rows = section.getByRole("row");
  await expect(rows.nth(1)).toContainText("VT");
  await expect(rows.nth(2)).toContainText("IWDA");
  const own = page.getByRole("region", { name: "What you own" });
  await expect(own.getByRole("listitem", { name: "Interactive Brokers" })).toContainText("25,350.40");
});
