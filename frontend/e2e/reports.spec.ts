import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Daily Report: Stitch design", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/reports");
  });

  test("renders page header with Daily Report title", async ({ page }) => {
    await expect(page.getByText("Daily Report")).toBeVisible();
    await expect(page.getByText("Automated daily safety analysis reports")).toBeVisible();
  });

  test("displays date navigation with current date", async ({ page }) => {
    const today = new Date();
    const monthName = today.toLocaleDateString("en-US", { month: "long" });
    await expect(page.getByText(new RegExp(monthName))).toBeVisible();
  });

  test("previous day button navigates to earlier date", async ({ page }) => {
    // There are left/right ChevronLeft/ChevronRight buttons
    const prevButton = page.locator("button").filter({ has: page.locator("svg") }).first();
    // Capture the date text before clicking
    const dateText = page.locator("span.min-w-56");
    const initialDate = await dateText.textContent();
    // The first SVG button in the date nav is the prev button
    await page.locator("button:has(svg.lucide-chevron-left)").click();
    await expect(dateText).not.toHaveText(initialDate!);
  });

  test("renders PDF download button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /pdf/i })).toBeVisible();
  });

  test("renders Markdown download button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /markdown/i })).toBeVisible();
  });

  test("report content area shows rendered markdown", async ({ page }) => {
    await expect(page.getByText("Daily Safety Report")).toBeVisible();
    await expect(page.getByText(/3 violations/)).toBeVisible();
  });

  test("report shows recommendations section", async ({ page }) => {
    await expect(page.getByText("Recommendations")).toBeVisible();
    await expect(page.getByText(/Review agent-alpha permissions/)).toBeVisible();
  });

  test("calendar icon is present in date navigation", async ({ page }) => {
    await expect(
      page.locator(".material-symbols-outlined").filter({ hasText: "calendar_today" }),
    ).toBeVisible();
  });
});
