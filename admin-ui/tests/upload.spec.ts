import { test, expect } from "@playwright/test";

test.describe("Upload Page", () => {
  test("drop zone is visible", async ({ page }) => {
    await page.goto("/upload");
    await expect(page.locator(".drop-zone")).toBeVisible();
    await expect(page.locator(".drop-zone")).toContainText("Drop file here");
  });

  test("category selector is present", async ({ page }) => {
    await page.goto("/upload");
    await expect(page.locator(".term-select")).toBeVisible();
  });
});
