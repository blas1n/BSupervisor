import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Cost Monitor", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/costs");
  });

  test("renders budget progress bar", async ({ page }) => {
    await expect(page.getByText("Cost Monitor")).toBeVisible();
    await expect(page.getByText("Daily Budget")).toBeVisible();
    await expect(page.getByText("$48.23 of $100.00")).toBeVisible();
    await expect(page.getByText("48.2%")).toBeVisible();
  });

  test("renders 30-day cost trend chart", async ({ page }) => {
    await expect(page.getByText("30-Day Cost Trend")).toBeVisible();
  });

  test("renders agent cost breakdown table", async ({ page }) => {
    await expect(page.getByText("Cost Breakdown by Agent")).toBeVisible();
    await expect(page.getByText("Alpha Assistant")).toBeVisible();
    await expect(page.getByText("Beta Processor")).toBeVisible();
    await expect(page.getByText("Gamma Worker")).toBeVisible();
  });

  test("anomaly agent is highlighted", async ({ page }) => {
    // agent-alpha is in anomalies list, should show "Anomaly" badge
    await expect(page.getByText("Anomaly")).toBeVisible();
  });

  test("navigation from sidebar works", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Safety Dashboard")).toBeVisible();
    await page.getByRole("link", { name: "Costs" }).click();
    await expect(page).toHaveURL("/costs");
    await expect(page.getByText("Cost Monitor")).toBeVisible();
  });
});
