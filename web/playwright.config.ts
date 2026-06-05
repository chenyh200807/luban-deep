import { defineConfig, devices } from "@playwright/test";

const BASE_URL =
  process.env.WEB_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:3000";
const SHOULD_START_WEB_SERVER =
  process.env.PW_START_WEB_SERVER === "1" &&
  process.env.PW_SKIP_WEB_SERVER !== "1" &&
  !process.env.WEB_BASE_URL &&
  !process.env.NEXT_PUBLIC_API_BASE;
const BI_V2_SERVER_ENV =
  process.env.PW_BI_V2 === "1"
    ? [
        "BI_BACKOFFICE_V2_SHELL_ENABLED=1",
        "BI_OVERVIEW_V2_ENABLED=1",
        "BI_CRM_V2_ENABLED=1",
        "BI_COMMERCE_V2_ENABLED=1",
        "BI_FEEDBACK_V2_ENABLED=1",
        "BI_SYSTEM_OPS_V2_ENABLED=1",
      ].join(" ")
    : "";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  webServer: SHOULD_START_WEB_SERVER
    ? {
        command: `${BI_V2_SERVER_ENV ? `${BI_V2_SERVER_ENV} ` : ""}npm run dev`,
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
