import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";

// Runs after the workbook and statement specs: the latest month has data. Without an API key
// (CI) the findings are written by rules.
test("report: write the month's findings, then download its transactions", async ({ page }) => {
  await page.goto("/report");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^\w+ \d{4} report$/);
  const write = page.getByRole("button", {
    name: /^(Write the report|Write the report with Claude|Regenerate)$/,
  });
  await write.click();
  const findings = page.getByRole("list", { name: "Findings" });
  await expect(findings.getByRole("listitem").first()).toBeVisible({ timeout: 60_000 });
  expect(await findings.getByRole("listitem").count()).toBeGreaterThanOrEqual(1);
  await expect(page.getByText(/^Written by /)).toBeVisible();
  await expect(page.getByRole("button", { name: "Regenerate" })).toBeVisible();

  const downloads = page.getByRole("list", { name: "Downloads" });
  const [file] = await Promise.all([
    page.waitForEvent("download"),
    downloads.getByRole("link", { name: "CSV of Transactions" }).click(),
  ]);
  expect(file.suggestedFilename()).toMatch(/^cashflow-transactions-\d{4}-\d{2}\.csv$/);
  const text = await readFile(await file.path(), "utf-8");
  expect(text.replace(/^\uFEFF/, "").split("\r\n")[0]).toContain("Txn date,Post date,Cash month,Account,Amount");

  const [xlsx] = await Promise.all([
    page.waitForEvent("download"),
    downloads.getByRole("link", { name: "Excel of Monthly cash flow (spending view)" }).click(),
  ]);
  expect(xlsx.suggestedFilename()).toMatch(/^cashflow-monthly-cashflow-\d{4}\.xlsx$/);
});
