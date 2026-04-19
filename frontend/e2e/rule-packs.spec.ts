import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Rule Template Packs", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
  });

  test("shows rule packs section on rules page", async ({ page }) => {
    await page.goto("/rules");
    await expect(page.getByText("Rule Template Packs")).toBeVisible();
    await expect(page.getByText("Pre-built safety rule collections")).toBeVisible();
  });

  test("displays all three packs", async ({ page }) => {
    await page.goto("/rules");
    await expect(page.getByTestId("pack-healthcare-hipaa")).toBeVisible();
    await expect(page.getByTestId("pack-financial-compliance")).toBeVisible();
    await expect(page.getByTestId("pack-langchain-agent")).toBeVisible();
  });

  test("shows pack details: name, category, rule count", async ({ page }) => {
    await page.goto("/rules");
    const pack = page.getByTestId("pack-healthcare-hipaa");
    await expect(pack.getByText("Healthcare HIPAA Pack")).toBeVisible();
    await expect(pack.getByText("4 rules")).toBeVisible();
    // Category badge exists
    await expect(pack.getByText("healthcare", { exact: true })).toBeVisible();
  });

  test("install button triggers installation", async ({ page }) => {
    await page.goto("/rules");
    const installBtn = page.getByTestId("install-healthcare-hipaa");
    await expect(installBtn).toHaveText("Install Pack");

    await installBtn.click();
    // After install, shows result
    await expect(installBtn).toContainText("installed");
  });
});
