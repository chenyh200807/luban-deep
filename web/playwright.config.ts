import { defineConfig, devices } from "@playwright/test";

const BASE_URL =
  process.env.WEB_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:3000";
const SERIAL_MODE = process.env.PW_SERIAL === "1";
const SHOULD_START_WEB_SERVER =
  process.env.PW_START_WEB_SERVER === "1" &&
  process.env.PW_SKIP_WEB_SERVER !== "1" &&
  !process.env.WEB_BASE_URL &&
  !process.env.NEXT_PUBLIC_API_BASE;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: !SERIAL_MODE,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: SERIAL_MODE ? 1 : undefined,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  webServer: SHOULD_START_WEB_SERVER
    ? {
        command: "npm run dev -- --hostname 127.0.0.1",
        url: BASE_URL,
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      }
    : undefined,
  projects: [
    {
      name: "ui-audit",
      testMatch: "**/*.audit.ts",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "wechat-harness",
      testMatch: "**/wechat-harness.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 980 },
      },
    },
  ],
});
