import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./tests",
  outputDir: "../.logs/playwright-results",
  fullyParallel: false,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:31415",
    channel: "chrome",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "desktop-chrome", use: { ...devices["Desktop Chrome"], channel: "chrome" } }],
})
