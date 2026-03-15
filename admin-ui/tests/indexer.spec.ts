import { test, expect } from "@playwright/test";

test.describe("Indexer Page", () => {
  test("status information is shown", async ({ page }) => {
    await page.goto("/indexer");
    await expect(page.locator(".page-title")).toHaveText("INDEXER");
    await expect(page.locator("text=Status")).toBeVisible();
    await expect(page.locator("text=Last Run")).toBeVisible();
  });

  test("run button is present", async ({ page }) => {
    await page.goto("/indexer");
    await expect(page.locator("text=[ RUN NOW ]")).toBeVisible();
  });

  test("output area is present", async ({ page }) => {
    await page.goto("/indexer");
    await expect(page.locator(".log-viewer")).toBeVisible();
  });
});
