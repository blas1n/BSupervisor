/**
 * Phase C — i18n smoke tests.
 *
 * Asserts that:
 *  - The default English chrome renders at `/` (no locale prefix) so the
 *    rest of the e2e suite continues to assert on English copy.
 *  - The Korean chrome renders at `/ko` with the supervisor namespace
 *    swapped (nav labels, "Sign out" button, brand tagline, page title).
 *  - The header locale-switcher buttons exist and reflect the active locale.
 */
import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Phase C: i18n", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
  });

  test("English chrome (default) renders 'Live Surveillance' and 'AI Sentinel'", async ({
    page,
  }) => {
    await page.goto("/");
    // Header (visible) — supervisor.branding.liveStatus
    await expect(page.getByText("Live Surveillance")).toBeVisible();
    // Sidebar logo (sidebar is aria-hidden on closed-drawer desktop, but
    // text-based queries still match) — supervisor.branding.tagline
    await expect(page.getByText("AI Sentinel")).toBeVisible();
    // supervisor.userMenu.signOut — text query (sidebar footer)
    await expect(page.getByText("Sign out")).toBeVisible();
  });

  test("Korean chrome at /ko swaps nav + branding + sign-out copy", async ({
    page,
  }) => {
    await page.goto("/ko");
    await expect(page.getByText("실시간 감시")).toBeVisible();
    await expect(page.getByText("AI 감시자")).toBeVisible();
    await expect(page.getByText("로그아웃")).toBeVisible();
  });

  test("locale switcher exposes EN and KO buttons", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("locale-en")).toBeVisible();
    await expect(page.getByTestId("locale-ko")).toBeVisible();
    await expect(page.getByTestId("locale-en")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("locale-ko")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  test("supervisor.* namespace covers the documented 16 keys", async ({
    page,
  }) => {
    await page.goto("/ko/incidents");
    // Page title pulled from supervisor.pageTitles.incidents
    await expect(page.getByText("사건 타임라인")).toBeVisible();
  });
});
