import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Daily Report", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/reports");
  });

  test("renders date navigation", async ({ page }) => {
    await expect(page.getByText("Daily Report")).toBeVisible();
    // Date should be displayed
    await expect(page.getByText(/Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday/)).toBeVisible();
  });

  test("renders report content", async ({ page }) => {
    await expect(page.getByText("Daily Safety Report")).toBeVisible();
    await expect(page.getByText(/3 violations/)).toBeVisible();
  });

  test("download buttons are visible", async ({ page }) => {
    await expect(page.getByText("PDF")).toBeVisible();
    await expect(page.getByText("Markdown")).toBeVisible();
  });

  test("date navigation buttons work", async ({ page }) => {
    // Get the current date text
    const dateText = page.locator("span.min-w-56");
    const initialDate = await dateText.textContent();

    // Click previous day
    const prevButton = page.locator("button").filter({ has: page.locator("svg.lucide-chevron-left") });
    await prevButton.click();

    // Date should change
    const newDate = await dateText.textContent();
    expect(newDate).not.toBe(initialDate);
  });
});
