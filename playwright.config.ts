import { randomInt } from "node:crypto";

import { defineConfig, devices } from "@playwright/test";

const configuredPort = process.env.ENTROPING_E2E_PORT;
const portValue = configuredPort ?? String(randomInt(20_000, 60_000));
process.env.ENTROPING_E2E_PORT = portValue;
const port = Number(portValue);

if (!Number.isInteger(port) || port < 1_024 || port > 65_535) {
  throw new Error(
    "ENTROPING_E2E_PORT must be an integer from 1024 through 65535",
  );
}

const baseURL = `http://127.0.0.1:${port}/Entroping/`;

export default defineConfig({
  testDir: "./tests/site",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  ...(process.env.CI ? { workers: 2 } : {}),
  reporter: process.env.CI ? "github" : "list",
  snapshotPathTemplate:
    "{testDir}/__screenshots__/{testFilePath}/{arg}-{platform}{ext}",
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      maxDiffPixelRatio: 0.02,
    },
  },
  use: {
    baseURL,
    colorScheme: "light",
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `npm run build:clean && npm run preview -- --host 127.0.0.1 --port ${port}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
