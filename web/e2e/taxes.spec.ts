import { expect, test } from "@playwright/test";

// ADR-088: the year's income tax, projected for each person, as a tab of Taxes.
test("income tax: the projection for both people", async ({ page }) => {
  await page.goto("/taxes");
  await page
    .getByRole("navigation", { name: "Taxes pages" })
    .getByRole("link", { name: "Income tax" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Income tax \d{4}$/);
  for (const who of ["Hernan", "Lauren"]) {
    const card = page.getByRole("region", { name: `${who}'s income tax` });
    await expect(card).toBeVisible();
    await expect(card.getByText("Tax by the SRI's table")).toBeVisible();
  }
});
