import { expect, test } from "@playwright/test";

import {
  expectNoHorizontalOverflow,
  responsiveViewports,
  waitForStablePage,
} from "./helpers";

test.describe("documentation entry", () => {
  test("leads with task-oriented first-hour paths", async ({ page }) => {
    await page.goto("./docs/");

    await expect(
      page.getByRole("heading", { level: 1, name: "Entroping Documentation" }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "Hurl is the deterministic local HTTP runner; Entroping adds policy, generation, and reviewable evidence around it.",
      ),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Run the local demo" })).toHaveAttribute(
      "href",
      "/Entroping/#demo",
    );
    await expect(page.getByRole("link", { name: "Protect an API" })).toHaveAttribute(
      "href",
      "/Entroping/docs/user/user-guide/#3-new-project-quick-start",
    );
    await expect(page.getByRole("link", { name: "Add the CI gate" })).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 2, name: "Browse by Topic" }),
    ).toBeVisible();
  });

  test("puts beginner guides ahead of maintainer-only demo assets", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("./docs/");

    const sidebar = page.getByRole("navigation", { name: /main/iu });
    await expect(sidebar.getByRole("link", { name: "User Guide" })).toBeVisible();
    await expect(
      sidebar.getByRole("link", { name: "Policy First Hour" }),
    ).toBeVisible();
    await expect(
      sidebar.getByRole("link", { name: "Demo Asset Reference" }),
    ).not.toBeVisible();
  });

  test("states alpha maturity and prerequisites on first-hour guides", async ({
    page,
  }) => {
    await page.goto("./docs/user/user-guide/");
    await expect(page.getByText("Product maturity: Alpha")).toBeVisible();
    await expect(page.getByText("Contract version: 4.1")).toBeVisible();

    await page.goto("./docs/user/qanstitution-first-hour/");
    await expect(
      page.getByRole("heading", { level: 2, name: "Before You Begin" }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "installation guide" })).toBeVisible();
  });

  test("publishes stable alpha scope without volatile tracker claims", async ({
    page,
  }) => {
    await page.goto("./docs/");
    const sidebar = page.getByRole("navigation", { name: /main/iu });
    await expect(sidebar.getByRole("link", { name: "Alpha Status" })).toHaveAttribute(
      "href",
      "/Entroping/docs/user/alpha-status/",
    );
    const navLabels = (await sidebar.getByRole("link").allTextContents()).map(
      (label) => label.trim(),
    );
    const reportSchemasIndex = navLabels.indexOf("Report Schemas");
    const alphaStatusIndex = navLabels.indexOf("Alpha Status");
    const technicalDesignIndex = navLabels.indexOf("Technical Design");
    expect(reportSchemasIndex).toBeGreaterThanOrEqual(0);
    expect(alphaStatusIndex).toBeGreaterThanOrEqual(0);
    expect(technicalDesignIndex).toBeGreaterThanOrEqual(0);
    expect(reportSchemasIndex).toBeLessThan(alphaStatusIndex);
    expect(alphaStatusIndex).toBeLessThan(technicalDesignIndex);

    await page.goto("./docs/user/alpha-status/");

    await expect(
      page.getByRole("heading", { level: 1, name: "Current Alpha Status" }),
    ).toBeVisible();
    await expect(page.getByText("Product maturity: Alpha")).toBeVisible();
    await expect(
      page.getByText(
        "Windows is currently a doctor-only alpha path; Hurl-backed entroping run on Windows is not yet a public support claim.",
      ),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "public roadmap" })).toHaveAttribute(
      "href",
      "https://github.com/sakibshuvo/Entroping/blob/main/ROADMAP.md",
    );
    await expect(
      page.getByRole("link", { name: "project progress dashboard" }),
    ).toHaveAttribute(
      "href",
      "https://github.com/sakibshuvo/Entroping/blob/main/docs/meta/PROJECT_PROGRESS.md",
    );
    await expect(page.getByRole("link", { name: "GitHub Issues" })).toHaveAttribute(
      "href",
      "https://github.com/sakibshuvo/Entroping/issues",
    );

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/#\d+/u);
    expect(bodyText).not.toMatch(
      /\b(?:production-ready|production ready|security guarantee|stable release)\b/iu,
    );
    expect(bodyText).not.toMatch(/(?:uv tool install|Hurl 4\.3|Hurl 8\.0)/iu);
  });

  for (const viewport of responsiveViewports) {
    test(`stays within the viewport at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("./docs/");
      await waitForStablePage(page);

      await expectNoHorizontalOverflow(page);
    });
  }

  test("searches for Hurl on a phone-sized viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 900 });
    await page.goto("./docs/");
    await page.getByRole("button", { name: /search/iu }).first().click();

    const search = page.getByPlaceholder("Search");
    await search.fill("Hurl");

    await expect(page.getByText(/results for Hurl/iu)).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("Entroping User Guide")).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel" })).toBeInViewport();
    await expectNoHorizontalOverflow(page);
  });
});
