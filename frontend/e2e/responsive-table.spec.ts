import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

/**
 * ResponsiveTable adoption coverage.
 *
 * The three data tables in BSupervisor's frontend — Rules Manager, Cost
 * Monitor, and the Dashboard "Top Triggered Rules" panel — now render via
 * the shared `@bsvibe/ui` <ResponsiveTable>. That component dual-renders:
 *   • a real <table> (wrapped in overflow-x-auto) for the `sm:` breakpoint
 *     and up — `data-testid="bsvibe-table-scroll"`.
 *   • a stack of <article data-testid="bsvibe-table-card"> below `sm:` —
 *     `data-testid="bsvibe-table-mobile"`.
 *
 * Tailwind's `sm:` is 640px. The Playwright `chromium` project runs at a
 * 1280px desktop viewport (table visible, cards hidden); the `pixel-5`
 * (393px) and `iphone-13` (390px) projects run below `sm:` (cards visible,
 * table hidden).
 *
 * Note: protected-page specs can fail in a browserless / SSO-mocked CI
 * environment for reasons unrelated to this component — that is a known
 * pre-existing limitation of the suite.
 */

const VIEWS = [
  { name: "Rules Manager", path: "/rules" },
  { name: "Cost Monitor", path: "/costs" },
  { name: "Dashboard Top Triggered Rules", path: "/" },
] as const;

test.describe("ResponsiveTable: desktop renders a <table>", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    // Desktop tree only — the < sm card stack is asserted below.
    testInfo.skip(
      testInfo.project.name !== "chromium",
      "Desktop-only: <table> is hidden below the sm breakpoint",
    );
    await injectAuth(page);
    await mockAllApis(page);
  });

  for (const view of VIEWS) {
    test(`${view.name} shows the desktop table`, async ({ page }) => {
      await page.goto(view.path);
      const scroll = page.locator("[data-testid='bsvibe-table-scroll']").first();
      await expect(scroll).toBeVisible();
      // The desktop scroll wrapper contains a real <table> with column headers.
      await expect(scroll.locator("table")).toBeVisible();
      await expect(scroll.locator("th").first()).toBeVisible();
      // The mobile card stack must NOT be visible at a desktop width.
      await expect(
        page.locator("[data-testid='bsvibe-table-card']").first(),
      ).toBeHidden();
    });
  }
});

test.describe("ResponsiveTable: mobile renders a card stack", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    // Card stack only — runs on the pixel-5 / iphone-13 mobile projects.
    testInfo.skip(
      testInfo.project.name === "chromium",
      "Mobile-only: the card stack is hidden at >= sm",
    );
    await injectAuth(page);
    await mockAllApis(page);
  });

  for (const view of VIEWS) {
    test(`${view.name} shows the mobile card stack`, async ({ page }) => {
      await page.goto(view.path);
      const cards = page.locator("[data-testid='bsvibe-table-card']");
      // At least one mocked row renders as a card.
      await expect(cards.first()).toBeVisible();
      expect(await cards.count()).toBeGreaterThan(0);
      // The desktop <table> is CSS-hidden below the sm breakpoint.
      await expect(page.locator("table").first()).toBeHidden();
    });
  }
});
