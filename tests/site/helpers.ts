import { expect, type Page } from "@playwright/test";

export const responsiveViewports = [
  { width: 320, height: 900 },
  { width: 375, height: 900 },
  { width: 768, height: 900 },
  { width: 1280, height: 900 },
] as const;

export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const diagnostics = await page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const round = (value: number) => Math.round(value * 100) / 100;
    const scrollingElement =
      document.scrollingElement ?? document.documentElement;
    const initialScrollX = window.scrollX;
    const initialScrollY = window.scrollY;
    const initialScrollBehavior = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = "auto";
    const overflow = document.documentElement.scrollWidth - viewportWidth;
    window.scrollTo(document.documentElement.scrollWidth, initialScrollY);
    const maxWindowScrollX = window.scrollX;
    const maxRootScrollLeft = scrollingElement.scrollLeft;
    window.scrollTo(initialScrollX, initialScrollY);
    document.documentElement.style.scrollBehavior = initialScrollBehavior;
    const offenders =
      overflow > 0 || maxWindowScrollX > 0 || maxRootScrollLeft > 0
        ? [document.body, ...document.body.querySelectorAll<HTMLElement>("*")]
            .map((element) => {
              const bounds = element.getBoundingClientRect();
              return {
                tag: element.tagName.toLowerCase(),
                id: element.id,
                className: element.getAttribute("class") ?? "",
                left: round(bounds.left),
                right: round(bounds.right),
                width: round(bounds.width),
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
              };
            })
            .filter(
              ({ left, right }) => left < -0.5 || right > viewportWidth + 0.5,
            )
            .slice(0, 12)
        : [];

    return {
      overflow,
      viewportWidth,
      documentClientWidth: document.documentElement.clientWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyClientWidth: document.body.clientWidth,
      bodyScrollWidth: document.body.scrollWidth,
      maxWindowScrollX,
      maxRootScrollLeft,
      offenders,
    };
  });
  const message = `Horizontal overflow diagnostics: ${JSON.stringify(diagnostics)}`;
  expect(
    diagnostics.overflow,
    message,
  ).toBeLessThanOrEqual(0);
  expect(diagnostics.maxWindowScrollX, message).toBe(0);
  expect(diagnostics.maxRootScrollLeft, message).toBe(0);
}

export async function waitForStablePage(page: Page): Promise<void> {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForLoadState("networkidle");
  await page.evaluate(async () => document.fonts.ready);
}
