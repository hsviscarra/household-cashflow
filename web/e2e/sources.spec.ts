import { expect, test } from "@playwright/test";

// Runs after the workbook spec. Statements count from January 2026: the workbook's January becomes
// a reference, checked against the statements; then the setting goes back so other specs see the
// workbook as before (one worker, so nothing runs in between; reset even if the test fails).
test.afterEach(async ({ request }) => {
  await request.put("/api/sources", { data: { statements_from: null } });
});

test("statements from a month: the workbook becomes a reference, then back", async ({ page }) => {
  await page.goto("/status");
  const section = page.getByRole("region", { name: "Where the numbers come from" });
  await expect(section).toContainText("The Cash Flow workbook counts through");
  const choose = section.getByLabel("Statements count from");
  await choose.selectOption("2026-01");
  await section.getByRole("button", { name: "Save" }).click();
  await expect(section).toContainText("From January 2026 the statements count");
  const check = section.getByRole("list", { name: "Workbook vs statements" });
  await expect(check.getByText("January 2026", { exact: true })).toBeVisible();
  await expect(check).toContainText("Spending: workbook");

  await choose.selectOption("");
  await section.getByRole("button", { name: "Save" }).click();
  await expect(section).toContainText("The Cash Flow workbook counts through");
  await expect(section.getByRole("list", { name: "Workbook vs statements" })).toHaveCount(0);
});
