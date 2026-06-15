import { defineConfig, devices } from "@playwright/test";

const WEB_SERVER_PORT = process.env.PW_WEB_PORT || "3000";
const BASE_URL =
  process.env.WEB_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  `http://127.0.0.1:${WEB_SERVER_PORT}`;
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
const WEB_SERVER_MODE = process.env.PW_WEB_SERVER_MODE || "dev";
const WEB_SERVER_COMMAND =
  WEB_SERVER_MODE === "standalone"
    ? `PORT=${WEB_SERVER_PORT} DEEPTUTOR_ENABLE_WECHAT_HARNESS=true npm run start:standalone:smoke`
    : `${BI_V2_SERVER_ENV ? `${BI_V2_SERVER_ENV} ` : ""}PORT=${WEB_SERVER_PORT} npm run dev`;

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
        command: WEB_SERVER_COMMAND,
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
