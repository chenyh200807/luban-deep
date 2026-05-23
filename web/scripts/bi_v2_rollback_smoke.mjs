#!/usr/bin/env node
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const BASE = process.env.BI_V2_BASE || "http://localhost:3001";
const OUT_DIR = process.env.BI_V2_SHOTS || "/tmp/bi-v2-shots";

mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));

  const resp = await page.goto(`${BASE}/bi`, { waitUntil: "domcontentloaded", timeout: 60000 });
  if (!resp || resp.status() >= 400) {
    console.error(`HTTP ${resp?.status() ?? "no-response"}`);
    process.exit(1);
  }
  await page.waitForLoadState("networkidle", { timeout: 30000 });

  const v2Count = await page.locator("[data-bi-v2-root]").count();
  if (v2Count > 0) {
    console.error("FAIL: BI v2 shell rendered even with flag disabled.");
    process.exit(1);
  }

  // legacy 老板工作台是旧 BiPageClient 默认 tab 的中文标识
  const legacyHasLegacyTab = await page
    .getByText("老板工作台")
    .first()
    .isVisible()
    .catch(() => false);

  const shotPath = resolve(OUT_DIR, "bi-v2-rollback-legacy-1440.png");
  await page.screenshot({ path: shotPath, fullPage: true });

  if (consoleErrors.length > 0) {
    console.error("Console errors during legacy render:");
    for (const e of consoleErrors.slice(0, 5)) console.error(" ", e);
    process.exit(1);
  }
  if (!legacyHasLegacyTab) {
    console.error("WARN: legacy BiPageClient tabs not detected by text 老板工作台.");
    // not fatal: bi-admin-auth gate may show login screen — still no v2 shell.
  }
  console.log(`OK · rollback verified · screenshot: ${shotPath}`);
} finally {
  await browser.close();
}
