import { expect, test } from "@playwright/test";

import { waitForStablePage } from "./helpers";

test("@visual protects the mobile launch composition", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("./");
  await waitForStablePage(page);

  await expect(page).toHaveScreenshot("launch-mobile.png");
});

test("@visual protects the mobile menu on a fresh page", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("./");
  await waitForStablePage(page);

  const menu = page.locator("details[data-nav-menu]");
  await page.locator("summary[aria-controls='launch-menu']").click();
  await expect(menu).toHaveAttribute("open", "");
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
  await expect(page).toHaveScreenshot("launch-mobile-menu.png");
});

test("@visual protects the desktop launch composition", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("./");
  await waitForStablePage(page);

  await expect(page).toHaveScreenshot("launch-desktop.png");
});

test("@visual protects the mobile docs entry and search state", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("./docs/");
  await waitForStablePage(page);

  await expect(page).toHaveScreenshot("docs-mobile.png");

  await page.getByRole("button", { name: /search/iu }).first().click();
  await page.getByPlaceholder("Search").fill("Hurl");
  await expect(page.getByText(/results for Hurl/iu)).toBeVisible({
    timeout: 10_000,
  });
  await expect(page).toHaveScreenshot("docs-search-mobile.png");
});

test("@visual protects visible clipboard recovery guidance", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
  });
  await page.goto("./#demo");
  await waitForStablePage(page);

  const codeWindow = page
    .getByRole("figure")
    .filter({ hasText: "Repository checkout" });
  await codeWindow.getByRole("button", { name: "Copy" }).click();
  await expect(
    codeWindow.getByText("Copy unavailable. Select the command manually."),
  ).toBeVisible();
  await expect(codeWindow).toHaveScreenshot("copy-unavailable.png");
});
