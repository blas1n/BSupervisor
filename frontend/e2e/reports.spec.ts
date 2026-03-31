import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Daily Report: Stitch design", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/reports");
  });

  test("renders page header with DAILY INTELLIGENCE BRIEF title", async ({ page }) => {
    await expect(page.getByText("DAILY INTELLIGENCE BRIEF")).toBeVisible();
  });

  test("displays status indicator", async ({ page }) => {
    await expect(page.getByText("Operational")).toBeVisible();
  });

  test("displays date navigation with current date", async ({ page }) => {
    const today = new Date();
    const monthName = today.toLocaleDateString("en-US", { month: "long" });
    await expect(page.getByText(new RegExp(monthName))).toBeVisible();
  });

  test("yesterday/tomorrow navigation buttons exist", async ({ page }) => {
    await expect(page.getByText("Yesterday")).toBeVisible();
    await expect(page.getByText("Tomorrow")).toBeVisible();
  });

  test("renders PDF download button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /pdf/i })).toBeVisible();
  });

  test("renders MD download button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /md/i })).toBeVisible();
  });

  test("report content area shows rendered markdown", async ({ page }) => {
    await expect(page.getByText("Daily Safety Report")).toBeVisible();
    await expect(page.getByText(/3 violations/)).toBeVisible();
  });

  test("report shows recommendations section", async ({ page }) => {
    await expect(page.getByText("Recommendations")).toBeVisible();
    await expect(page.getByText(/Review agent-alpha permissions/)).toBeVisible();
  });

  test("report card has accent bar", async ({ page }) => {
    const accentBar = page.locator("section .bg-gradient-to-b");
    await expect(accentBar).toBeVisible();
  });

  test("event icon present in date navigation", async ({ page }) => {
    await expect(
      page.locator(".material-symbols-outlined").filter({ hasText: "event" }),
    ).toBeVisible();
  });
});
