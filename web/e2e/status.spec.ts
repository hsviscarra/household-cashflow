import { expect, test } from "@playwright/test";

// Runs after the statement and workbook specs: each month from the sheet's end to today is either
// complete or lists what is missing, with a link to fix it.
test("data status: each month is complete or says what is missing", async ({ page }) => {
  await page.goto("/status");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /^[A-Z][a-z]+ \d{4}: (complete|\d+ things? missing)$/,
  );
  const months = page.getByRole("list", { name: "Months" });
  await expect(months.getByRole("listitem").first()).toBeVisible();
  await expect(
    page.getByText(/^Through [A-Z][a-z]+ \d{4}: complete, from the Cash Flow sheet\.$/),
  ).toBeVisible();
  await expect(page.getByRole("table", { name: "Statement coverage by account and month" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Latest loads" })).toContainText("Statement");

  // The latest month is open; a missing statement links to the Import page.
  const upload = months.getByRole("link", { name: /^Upload for / }).first();
  await upload.click();
  await expect(page).toHaveURL(/\/import$/);
});
