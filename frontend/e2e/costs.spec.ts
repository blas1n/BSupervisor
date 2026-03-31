import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis, mockCosts } from "./helpers";

test.describe("Cost Monitor: Stitch design", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/costs");
  });

  test("renders page header with Cost Monitor title", async ({ page }) => {
    await expect(page.getByText("Cost Monitor")).toBeVisible();
    await expect(page.getByText("Track and optimize AI agent spending")).toBeVisible();
  });

  test("renders Daily Budget section with budget bar", async ({ page }) => {
    await expect(page.getByText("Daily Budget")).toBeVisible();
    await expect(page.getByText(`${mockCosts.spent} of ${mockCosts.budget}`)).toBeVisible();
  });

  test("displays budget percentage", async ({ page }) => {
    await expect(page.getByText("48.2%")).toBeVisible();
  });

  test("renders 30-Day Cost Trend chart area", async ({ page }) => {
    await expect(page.getByText("30-Day Cost Trend")).toBeVisible();
    await expect(page.getByText("Daily Spending Overview")).toBeVisible();
  });

  test("renders Cost Breakdown by Agent table", async ({ page }) => {
    await expect(page.getByText("Cost Breakdown by Agent")).toBeVisible();
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
    // Cost legend dot
    await expect(page.getByText("Cost").first()).toBeVisible();
    // Budget legend dashed line
    await expect(page.getByText("Budget").first()).toBeVisible();
  });

  test("wallet icon is present in budget section", async ({ page }) => {
    await expect(
      page.locator(".material-symbols-outlined").filter({ hasText: "account_balance_wallet" }).first(),
    ).toBeVisible();
  });
});
