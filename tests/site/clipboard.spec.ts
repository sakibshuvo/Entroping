import { expect, test, type Page } from "@playwright/test";

function repositoryCopyButton(page: Page) {
  return page
    .getByRole("figure")
    .filter({ hasText: "Repository checkout" })
    .getByRole("button");
}

test.describe("demo command copy", () => {
  test("copies the complete repository command", async ({ context, page }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("./#demo");

    const copyButton = repositoryCopyButton(page);
    await copyButton.click();

    await expect(copyButton).toHaveAccessibleName("Copied");
    await expect(page.getByText("Copied command.")).toBeVisible();
    await expect
      .poll(async () => page.evaluate(async () => navigator.clipboard.readText()))
      .toBe(
        "git clone https://github.com/sakibshuvo/Entroping.git\ncd Entroping\nbrew install uv hurl\nscripts/demo.sh",
      );
  });

  test("reports when clipboard access is unavailable", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: undefined,
      });
    });
    await page.goto("./#demo");

    await repositoryCopyButton(page).click();

    await expect(
      page.getByText("Copy unavailable. Select the command manually."),
    ).toBeVisible();
    await expect(repositoryCopyButton(page)).toHaveAccessibleName(
      "Copy unavailable",
    );
    await expect(repositoryCopyButton(page)).toBeDisabled();
  });

  test("recovers when the browser rejects clipboard access", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: () =>
            Promise.reject(new DOMException("Denied", "NotAllowedError")),
        },
      });
    });
    await page.goto("./#demo");

    await repositoryCopyButton(page).click();

    await expect(
      page.getByText("Copy failed. Select the command manually."),
    ).toBeVisible();
    await expect(repositoryCopyButton(page)).toHaveAccessibleName(
      "Try copy again",
    );
    await expect(repositoryCopyButton(page)).toBeEnabled();
  });

  test("resets visible copy state when a later permission attempt fails", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      let attempts = 0;
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: () => {
            attempts += 1;
            return attempts === 1
              ? Promise.resolve()
              : Promise.reject(new DOMException("Denied", "NotAllowedError"));
          },
        },
      });
    });
    await page.goto("./#demo");

    const copyButton = repositoryCopyButton(page);
    await copyButton.click();
    await expect(copyButton).toHaveAccessibleName("Copied");
    await copyButton.click();

    await expect(copyButton).toHaveAccessibleName("Try copy again");
    await expect(
      page.getByText("Copy failed. Select the command manually."),
    ).toBeVisible();
  });

  test("does not mask unexpected clipboard TypeErrors", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: () => Promise.reject(new TypeError("Unexpected copy error")),
        },
      });
    });
    await page.goto("./#demo");

    await repositoryCopyButton(page).click();

    await expect.poll(() => pageErrors).toContain("Unexpected copy error");
  });

  test("binds one clipboard write per copy click", async ({ page }) => {
    await page.addInitScript(() => {
      window.__copyAttempts = 0;
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: () => {
            window.__copyAttempts += 1;
            return Promise.resolve();
          },
        },
      });
    });
    await page.goto("./#demo");

    await repositoryCopyButton(page).click();

    await expect.poll(() => page.evaluate(() => window.__copyAttempts)).toBe(1);
  });

  test("retries successfully after a stalled clipboard write times out", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      let attempts = 0;
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: () => {
            attempts += 1;
            return attempts === 1
              ? new Promise<void>(() => {})
              : Promise.resolve();
          },
        },
      });
    });
    await page.goto("./#demo");

    await repositoryCopyButton(page).click();

    await expect(
      page.getByText(
        "Copy timed out. Try copy again or select the command manually.",
      ),
    ).toBeVisible({ timeout: 3_000 });
    const copyButton = repositoryCopyButton(page);
    await expect(copyButton).toHaveAccessibleName("Try copy again");
    await expect(copyButton).toBeEnabled();

    await copyButton.click();

    await expect(copyButton).toHaveAccessibleName("Copied");
  });
});

declare global {
  interface Window {
    __copyAttempts: number;
  }
}
