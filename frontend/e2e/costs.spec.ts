import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis, mockCosts } from "./helpers";

test.describe("Cost Monitor: Stitch design", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/costs");
  });

  test("renders budget progress section with consumption label", async ({ page }) => {
    await expect(page.getByText("Current Day Consumption")).toBeVisible();
    await expect(page.getByText(mockCosts.spent)).toBeVisible();
    await expect(page.getByText(`/ ${mockCosts.budget} Budget`)).toBeVisible();
  });

  test("renders Daily Cost Evolution section header", async ({ page }) => {
    await expect(page.getByText("Daily Cost Evolution (30D)")).toBeVisible();
  });

  test("renders Executor Breakdown table section", async ({ page }) => {
    await expect(page.getByText("Executor Breakdown")).toBeVisible();
  });

  test("agent table shows all column headers", async ({ page }) => {
    await expect(page.getByRole("columnheader", { name: /agent/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /requests/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /tokens/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /cost/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /%/ })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /trend/i })).toBeVisible();
  });

  test("displays all agents in the table", async ({ page }) => {
    await expect(page.getByText("Alpha Assistant")).toBeVisible();
    await expect(page.getByText("Beta Processor")).toBeVisible();
    await expect(page.getByText("Gamma Worker")).toBeVisible();
  });

  test("anomaly agent shows warning icon and Anomaly badge", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "Alpha Assistant" });
    await expect(row.locator(".material-symbols-outlined").filter({ hasText: "warning" })).toBeVisible();
    await expect(row.getByText("Anomaly")).toBeVisible();
  });

  test("trend chart shows legend for Cost and Budget lines", async ({ page }) => {
    await expect(page.getByText("Cost").first()).toBeVisible();
    await expect(page.getByText("Budget").first()).toBeVisible();
  });

  test("budget progress bar shows percentage markers", async ({ page }) => {
    await expect(page.getByText("0%").first()).toBeVisible();
    await expect(page.getByText("50%").first()).toBeVisible();
    await expect(page.getByText("100%").first()).toBeVisible();
  });
});
