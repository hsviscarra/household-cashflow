import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic BofA combined statement: a 25.00 move from checking to savings shows on both accounts.
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-bofa-full.pdf", import.meta.url));

test("transfers: both sides are matched, and the cash view counts card payments", async ({ page }) => {
  // Make sure the statement is loaded (the BofA spec may have done it already).
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible();
  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-bofa-full.pdf" });
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) await read.click();
  else await row.getByRole("link", { name: /Review|View/ }).click();
  const approve = page.getByRole("button", { name: "Approve import" });
  // Wait for the batch page to load: either it can be approved or it is already loaded.
  await expect(approve.or(page.getByText(/Loaded by/)).first()).toBeVisible();
  if (await approve.isVisible()) {
    await approve.click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  }

  // Each side of the checking → savings move names the other account.
  await page.goto("/transactions?month=2026-08");
  await expect(
    page
      .getByText(/↔ BofA Regular Savings/)
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  await expect(
    page
      .getByText(/↔ BofA Adv Plus Banking/)
      .filter({ visible: true })
      .first(),
  ).toBeVisible();

  // The card payment's other side (the Capital One statement) may not be loaded: Review lists it.
  await page.goto("/review?month=2026-08");
  await expect(page.getByRole("heading", { level: 1, name: "Review" })).toBeVisible();

  await page.goto("/");
  await page.getByRole("button", { name: "Cash view" }).click();
  await expect(page.getByRole("button", { name: "Cash view" })).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/view=cash/);
  await expect(page.getByText(/\+ card payments/)).toBeVisible();
  await page.getByRole("button", { name: "Spending view" }).click();
  await expect(page.getByText(/\+ card payments/)).toHaveCount(0);
});
