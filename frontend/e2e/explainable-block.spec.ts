import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis, mockEventsWithExplanation } from "./helpers";

test.describe("Explainable Block", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.route("**/api/events", (route) =>
      route.fulfill({ json: mockEventsWithExplanation }),
    );
  });

  test("blocked event in feed is clickable", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("file_write /etc/passwd")).toBeVisible();
  });

  test("clicking blocked event shows explanation panel", async ({ page }) => {
    await page.goto("/");
    await page.getByText("file_write /etc/passwd").click();

    const panel = page.getByTestId("explanation-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByText("Why this was blocked")).toBeVisible();
    await expect(panel.getByText("Blocks deletion of sensitive credential files")).toBeVisible();
    await expect(panel.getByText(".env")).toBeVisible();
  });

  test("explanation shows suggestion when available", async ({ page }) => {
    await page.goto("/");
    await page.getByText("file_write /etc/passwd").click();

    const panel = page.getByTestId("explanation-panel");
    await expect(panel.getByText("Use a secrets manager instead")).toBeVisible();
  });

  test("safe event does not show explanation", async ({ page }) => {
    await page.goto("/");
    await page.getByText("read_file config.yaml").click();
    await expect(page.getByTestId("explanation-panel")).not.toBeVisible();
  });
});
