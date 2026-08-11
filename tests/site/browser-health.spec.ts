import { expect, test, type Page } from "@playwright/test";

function collectBrowserIssues(page: Page): string[] {
  const issues: string[] = [];
  const servedOrigins = new Set<string>();

  page.on("request", (request) => {
    if (request.isNavigationRequest() && request.frame() === page.mainFrame()) {
      servedOrigins.add(new URL(request.url()).origin);
    }
  });

  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      issues.push(`console ${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => {
    issues.push(`pageerror: ${error.message}`);
  });
  page.on("requestfailed", (request) => {
    issues.push(`requestfailed: ${request.url()}`);
  });
  page.on("response", (response) => {
    if (
      servedOrigins.has(new URL(response.url()).origin) &&
      response.status() >= 400
    ) {
      issues.push(`response ${response.status()}: ${response.url()}`);
    }
  });

  return issues;
}

for (const route of ["./", "./docs/"] as const) {
  test(`${route} has a healthy browser runtime`, async ({ page }) => {
    const issues = collectBrowserIssues(page);

    await page.goto(route);
    await page.waitForLoadState("networkidle");

    await expect(page).toHaveTitle(/Entroping/);
    await expect(page.locator('meta[name="description"]')).toHaveAttribute(
      "content",
      /.+/,
    );

    expect(issues).toEqual([]);
  });
}
