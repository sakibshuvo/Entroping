import { expect, test } from "@playwright/test";

import {
  expectNoHorizontalOverflow,
  responsiveViewports,
  waitForStablePage,
} from "./helpers";

test.describe("launch page", () => {
  for (const viewport of responsiveViewports) {
    test(`explains the product without horizontal overflow at ${viewport.width}px`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport);
      await page.goto("./");
      await waitForStablePage(page);

      await expect(
        page.getByRole("heading", {
          level: 1,
          name: "Code at the speed of AI. Don't crash at the speed of AI.",
        }),
      ).toBeVisible();
      await expect(
        page.getByRole("region", { name: /code at the speed of ai/iu }).getByText(
          "Local-first runtime governance for AI-assisted backend teams.",
        ),
      ).toBeInViewport();
      await expect(
        page.getByText(
          "Catch status, auth, schema, and latency regressions before merge. Entroping keeps API integrity reviewable by turning specs, reviewed traffic, and policy into deterministic checks and CI-ready evidence.",
        ),
      ).toBeInViewport();
      await expectNoHorizontalOverflow(page);
    });
  }

  test("opens the mobile menu and exposes navigation state", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 900 });
    await page.goto("./");

    const menuButton = page.locator(
      "summary[aria-controls='launch-menu'][aria-expanded]",
    );
    await expect(menuButton).toHaveAccessibleName("Open navigation menu");
    await expect(menuButton).toHaveAttribute("aria-expanded", "false");
    await menuButton.click();
    await expect(menuButton).toHaveAccessibleName("Close navigation menu");
    await expect(menuButton).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#launch-menu").getByRole("link", { name: "Docs" })).toBeVisible();
    await expect(
      page.locator("#launch-menu").getByRole("link", { name: "GitHub" }),
    ).toBeVisible();
  });

  test("runs the API proof CTA into the concrete demo", async ({ page }) => {
    await page.goto("./");

    await page
      .getByRole("region", { name: /code at the speed of ai/iu })
      .getByRole("link", { name: "Run a 2-minute API proof" })
      .click();

    await expect(page).toHaveURL(/#demo$/u);
    await expect(
      page.getByRole("heading", { level: 2, name: "Test a sample API locally." }),
    ).toBeInViewport();
  });

  test("explains the proof flow before internal terminology", async ({ page }) => {
    await page.goto("./");

    await expect(
      page.getByRole("heading", {
        level: 3,
        name: "Specs or reviewed traffic become executable API tests.",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        level: 3,
        name: "Versioned policy enforces status, schema, auth, and latency.",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        level: 3,
        name: "Local and CI runs produce JSON, JUnit, and HTML evidence.",
      }),
    ).toBeVisible();

    const firstStep = page.locator(".proof-rail__step").first();
    expect(
      await firstStep.evaluate((step) => {
        const heading = step.querySelector("h3");
        const label = step.querySelector(".proof-rail__label");
        return heading?.nextElementSibling === label;
      }),
    ).toBe(true);
  });

  test("keeps the product category and proof CTA consistent", async ({ page }) => {
    await page.goto("./");

    await expect(
      page.getByText(
        "Local-first runtime governance for AI-assisted backend teams.",
      ),
    ).toHaveCount(2);
    await expect(
      page.getByRole("link", { name: "Run a 2-minute API proof" }),
    ).toHaveCount(2);
  });

  test("links non-macOS users to cross-platform setup", async ({ page }) => {
    await page.goto("./#demo");

    await expect(
      page.getByRole("link", { name: "Linux setup and Windows support status" }),
    ).toHaveAttribute("href", /docs\/user\/user-guide\/#2-install$/u);
    await expect(
      page.getByText(
        "Windows is currently limited to doctor checks; the API proof is not yet supported there.",
      ),
    ).toBeVisible();
  });

  test("keeps the complete mobile hero action set in the first viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 900 });
    await page.goto("./");
    await waitForStablePage(page);

    const hero = page.getByRole("region", { name: /code at the speed of ai/iu });
    await expect(hero.getByRole("link", { name: "Read the docs" })).toBeInViewport();
    await expect(
      page.getByRole("region", { name: "Chaos in. Proof out." }),
    ).toBeInViewport();
  });

  test("keeps both desktop CTA labels on one line", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("./");

    const hero = page.getByRole("region", { name: /code at the speed of ai/iu });
    for (const name of ["Run a 2-minute API proof", "Read the docs"] as const) {
      const label = hero.getByRole("link", { name }).locator("span");
      const lineCount = await label.evaluate((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        return range.getClientRects().length;
      });
      expect(lineCount).toBe(1);
    }
  });

});
