import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Incidents Page", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
  });

  test("shows incident list", async ({ page }) => {
    await page.goto("/incidents");
    await expect(page.getByText("Incident Timeline")).toBeVisible();
    await expect(page.getByText("Incidents (2)")).toBeVisible();
    await expect(page.getByText("Blocked file_delete: /secrets/private.key")).toBeVisible();
    await expect(page.getByText("Blocked shell_exec: sudo rm -rf /")).toBeVisible();
  });

  test("shows open and resolved status badges", async ({ page }) => {
    await page.goto("/incidents");
    await expect(page.getByText("open")).toBeVisible();
    await expect(page.getByText("resolved")).toBeVisible();
  });

  test("shows timeline when incident is selected", async ({ page }) => {
    await page.goto("/incidents");
    await page.getByTestId("incident-inc-1").click();

    // Timeline should be visible with entries
    await expect(page.getByTestId("timeline-entry").first()).toBeVisible();
    await expect(page.getByText("/secrets/private.key")).toBeVisible();
    await expect(page.getByText("/app/.env")).toBeVisible();
  });

  test("shows allowed and blocked entries in timeline", async ({ page }) => {
    await page.goto("/incidents");
    await page.getByTestId("incident-inc-1").click();

    await expect(page.getByText("Allowed")).toBeVisible();
    await expect(page.getByText("Blocked").first()).toBeVisible();
  });

  test("resolve button changes status", async ({ page }) => {
    await page.goto("/incidents");
    await page.getByTestId("incident-inc-1").click();

    const resolveBtn = page.getByTestId("resolve-btn");
    await expect(resolveBtn).toBeVisible();
    await resolveBtn.click();

    // After resolve, button should disappear
    await expect(resolveBtn).not.toBeVisible();
  });

  test("empty state when no incident selected", async ({ page }) => {
    await page.goto("/incidents");
    await expect(page.getByText("Select an incident to view its timeline")).toBeVisible();
  });
});
