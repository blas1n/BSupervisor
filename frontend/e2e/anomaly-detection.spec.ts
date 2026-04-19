import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Anomaly Detection", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
  });

  test("shows anomaly badge on flagged agent", async ({ page }) => {
    await page.goto("/costs");
    await expect(page.getByTestId("anomaly-badge")).toBeVisible();
    await expect(page.getByTestId("anomaly-badge")).toHaveText("Anomaly");
  });

  test("shows anomaly detail with multiplier and baseline", async ({ page }) => {
    await page.goto("/costs");
    const detail = page.getByTestId("anomaly-detail");
    await expect(detail).toBeVisible();
    await expect(detail).toContainText("3.5x above baseline");
    await expect(detail).toContainText("avg: 10.00");
  });

  test("non-anomaly agents do not show badge", async ({ page }) => {
    await page.goto("/costs");
    // Beta and Gamma agents should not have anomaly badge
    const badges = page.getByTestId("anomaly-badge");
    await expect(badges).toHaveCount(1); // only alpha
  });
});
