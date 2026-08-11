import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const routes = ["./", "./docs/"] as const;

for (const route of routes) {
  test(`${route} meets automated WCAG A and AA checks`, async ({
    page,
  }) => {
    await page.goto(route);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });
}

test("the launch page exposes keyboard and reduced-motion behavior", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("./");

  expect(
    await page.evaluate(
      () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();

  const animationName = await page
    .locator(".glyph-field__mark")
    .first()
    .evaluate((element) => getComputedStyle(element).animationName);
  expect(animationName).toBe("none");
});
