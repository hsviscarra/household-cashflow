import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic statements from api/tests/fixtures/statements.py. The second project finds them
// already uploaded, which is the duplicate check working.
const sample = (name: string) => fileURLToPath(new URL(`./fixtures/sample-${name}.pdf`, import.meta.url));
const ALL = ["bofa", "capitalone", "pichincha", "produbanco", "diners", "unknown"];

test("upload statements, see them detected, and a re-upload is refused", async ({ page }) => {
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(ALL.map(sample));
  await expect(page.getByText("6 files chosen", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 6 saved\./)).toBeVisible();

  const table = page.getByRole("table", { name: "Uploaded statements" });
  const row = (file: string) => table.getByRole("row").filter({ hasText: file });
  await expect(row("sample-bofa.pdf")).toContainText("BofA Regular Savings");
  await expect(row("sample-bofa.pdf")).toContainText("Aug 22, 2026 – Sep 22, 2026");
  await expect(row("sample-capitalone.pdf")).toContainText("Capital One Venture");
  await expect(row("sample-produbanco.pdf")).toContainText("Produbanco Ahorros Hernan");
  await expect(row("sample-unknown.pdf")).toContainText("Unknown format");

  // Diners is matched by the cardholder's name; the picker only shows if that fails.
  const picker = page.getByLabel("Account for sample-diners.pdf");
  if (await picker.isVisible()) {
    await picker.selectOption({ label: "Diners Club Hernan" });
    await row("sample-diners.pdf").getByRole("button", { name: "Save" }).click();
  }
  await expect(row("sample-diners.pdf")).toContainText("Diners Club Hernan");

  await page.getByLabel("Statement PDFs").setInputFiles(sample("capitalone"));
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText("0 of 1 saved.")).toBeVisible();
  await expect(page.getByText("Already uploaded", { exact: true })).toBeVisible();

  const pdf = await page.request.get(
    (await table.getByRole("link", { name: "sample-bofa.pdf" }).getAttribute("href")) ?? "",
  );
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
});
