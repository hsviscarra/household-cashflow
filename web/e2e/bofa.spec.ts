import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic BofA combined statement (api/tests/fixtures/statements.py: bofa_full).
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-bofa-full.pdf", import.meta.url));

test("read a BofA combined statement: both accounts tie out and load", async ({ page }) => {
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible();

  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-bofa-full.pdf" });
  // First run reads the lines; a re-run finds the preview or the loaded import.
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) await read.click();
  else await row.getByRole("link", { name: /Review|View/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "BofA Adv Plus Banking, BofA Regular Savings",
  );
  await expect(page.getByText("Ties out to the statement")).toBeVisible();
  await expect(page.getByText("•••• 8872 beginning balance + lines = ending balance")).toBeVisible();
  await expect(page.getByText("•••• 1862 beginning balance + lines = ending balance")).toBeVisible();
  const approve = page.getByRole("button", { name: "Approve import" });
  if (await approve.isVisible()) {
    await approve.click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  } else {
    await expect(page.getByText(/Loaded by/)).toBeVisible();
  }

  await page.goto("/transactions?month=2026-08");
  await expect(page.getByText("Monthly Maintenance Fee").filter({ visible: true })).toBeVisible();
  await expect(page.getByText("BofA Regular Savings").filter({ visible: true }).first()).toBeVisible();
});
