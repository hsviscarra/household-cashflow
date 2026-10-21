import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic Produbanco savings statement (api/tests/fixtures/statements.py: produbanco_full).
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-produbanco-full.pdf", import.meta.url));

test("read a Produbanco statement: running balance ties out, IESS split by amount", async ({ page }) => {
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible();

  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-produbanco-full.pdf" });
  // First run reads the lines; a re-run finds the preview or the loaded import.
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) await read.click();
  else await row.getByRole("link", { name: /Review|View/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Produbanco Ahorros Hernan, Jul 1, 2026 – Jul 31, 2026",
  );
  await expect(page.getByText("Ties out to the statement")).toBeVisible();
  await expect(page.getByText("Gaps in the running balance, line by line")).toBeVisible();
  // Two "PAGO IESS BANCA EN LINEA" lines, told apart by amount.
  for (const path of ["Household Staff / Empleada IESS", "Housing / Mortgage BIESS"])
    await expect(page.getByText(path, { exact: true }).filter({ visible: true }).first()).toBeVisible();

  const approve = page.getByRole("button", { name: "Approve import" });
  if (await approve.isVisible()) {
    await approve.click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  } else {
    await expect(page.getByText(/Loaded by/)).toBeVisible();
  }

  await page.goto("/transactions?month=2026-07");
  await expect(page.getByText("Produbanco Ahorros Hernan").filter({ visible: true }).first()).toBeVisible();
});
