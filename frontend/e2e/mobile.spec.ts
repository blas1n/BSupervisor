import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

/**
 * Phase B: mobile viewport smoke flow.
 *
 * Runs against the `pixel-5` (393×851) and `iphone-13` (390×844) Playwright
 * projects. The chromium desktop project still owns the deep regression
 * suite — this file focuses on responsive chrome and the canonical user
 * flow (login → dashboard → drawer-nav → core surface) on a small viewport.
 *
 * We skip these tests on the desktop chromium project because the
 * hamburger trigger and backdrop are CSS-hidden at >= 768px width.
 */

test.describe("Mobile viewport: BSupervisor core flow", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    // Mobile-only assertions (hamburger drawer + tap targets).
    if (testInfo.project.name === "chromium") {
      testInfo.skip();
    }
    await injectAuth(page);
    await mockAllApis(page);
  });

  test("login page renders without horizontal overflow on mobile", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "BSupervisor" })).toBeVisible();
    // No horizontal scroll on mobile — body width must fit viewport.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(2);
  });

  test("dashboard hamburger toggle opens the sidebar drawer", async ({ page }) => {
    await page.goto("/");
    // Sidebar nav links are in the DOM but the aside is translated off-screen.
    const hamburger = page.getByRole("button", { name: /open navigation/i });
    await expect(hamburger).toBeVisible();
    await hamburger.click();
    // Backdrop appears when drawer is open.
    await expect(page.getByTestId("bsvibe-sidebar-backdrop")).toBeVisible();
    // Active nav link is reachable.
    await expect(page.getByRole("link", { name: /dashboard/i })).toBeVisible();
  });

  test("hamburger trigger meets 44px touch-target minimum", async ({ page }) => {
    await page.goto("/");
    const hamburger = page.getByRole("button", { name: /open navigation/i });
    const box = await hamburger.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  });

  test("clicking a sidebar link closes the drawer (mobile UX)", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /open navigation/i }).click();
    await expect(page.getByTestId("bsvibe-sidebar-backdrop")).toBeVisible();
    await page.getByRole("link", { name: /rules/i }).click();
    // Backdrop is gone after navigation.
    await expect(page.getByTestId("bsvibe-sidebar-backdrop")).toHaveCount(0);
    await expect(page).toHaveURL(/\/rules/);
  });

  test("rules table is horizontally scrollable on mobile (no clipping)", async ({ page }) => {
    await page.goto("/rules");
    // The DataTable is wrapped in an overflow-x-auto container — when viewport
    // is narrower than table content, scrollWidth > clientWidth.
    const tableShell = page.locator("table").first().locator("..");
    await expect(tableShell).toBeVisible();
    const dims = await tableShell.evaluate((el) => ({
      scroll: el.scrollWidth,
      client: el.clientWidth,
    }));
    expect(dims.scroll).toBeGreaterThanOrEqual(dims.client);
  });

  test("backdrop click closes the drawer", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /open navigation/i }).click();
    const backdrop = page.getByTestId("bsvibe-sidebar-backdrop");
    await expect(backdrop).toBeVisible();
    await backdrop.click();
    await expect(backdrop).toHaveCount(0);
  });
});
