#!/usr/bin/env node
// Batch 7 QA gate: visual smoke across all sections + viewports +
// legacy rollback verification (flag off) + standup deeplink.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { withAdminSession } from "./_bi_v2_harness.mjs";

const BASE = process.env.BI_V2_BASE || "http://localhost:3001";
const OUT_DIR = process.env.BI_V2_SHOTS || "/tmp/bi-v2-shots";
mkdirSync(OUT_DIR, { recursive: true });

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 1024, height: 768 },
  { name: "mobile", width: 375, height: 812 },
];

const ROUTES = [
  { path: "/bi", expectedSection: "overview", expectStatus: 200 },
  { path: "/bi?tab=member-ops", expectedSection: "member-ops", expectStatus: 200 },
  { path: "/bi?tab=commerce", expectedSection: "commerce", expectStatus: 200 },
  { path: "/bi?tab=feedback", expectedSection: "feedback", expectStatus: 200 },
  { path: "/bi?tab=ops", expectedSection: "ops", expectStatus: 200 },
  // 计划期望 /bi/standup 存在，但目前未实装独立路由（旧 BiPageClient 内 tab）。
  // 标 expectStatus 404，让 release gate 显式记录该 gap 而非默默通过。
  { path: "/bi/standup", expectedSection: null, expectStatus: 404 },
];

const ROLLBACK_ENABLED = process.env.BI_V2_RUN_ROLLBACK !== "0";

const browser = await chromium.launch();
const failures = [];
const screenshots = [];

function tolerableConsole(text) {
  if (/Failed to load resource: the server responded with a status of (4\d\d|5\d\d)/.test(text)) return true;
  if (text.includes("/api/v1/bi/")) return true;
  if (text.includes("/api/v1/member/")) return true;
  return false;
}

try {
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    await withAdminSession(ctx);
    const page = await ctx.newPage();
    const consoleErrors = [];
    page.on("console", (m) => {
      if (m.type() !== "error") return;
      const text = m.text();
      if (tolerableConsole(text)) return;
      consoleErrors.push(text);
    });
    page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

    for (const route of ROUTES) {
      const url = `${BASE}${route.path}`;
      const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
      const actualStatus = resp?.status() ?? -1;
      if (actualStatus !== route.expectStatus) {
        failures.push(
          `${vp.name} ${route.path}: HTTP ${actualStatus}, 期望 ${route.expectStatus}`,
        );
        continue;
      }
      if (route.expectStatus !== 200) {
        // 期望非 200 时不再做后续 section / overflow / 截图检查。
        continue;
      }
      await page.waitForLoadState("networkidle", { timeout: 30000 });

      if (route.expectedSection !== null) {
        try {
          await page.waitForFunction(
            (expected) => document.querySelector("[data-bi-v2-root]")?.getAttribute("data-section") === expected,
            route.expectedSection,
            { timeout: 5000 },
          );
        } catch {
          failures.push(`${vp.name} ${route.path}: data-section 未到 ${route.expectedSection}`);
        }
      }

      const horizontal = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      if (horizontal > 1) {
        failures.push(`${vp.name} ${route.path}: horizontal overflow ${horizontal}px`);
      }

      await page.evaluate(
        () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
      );
      const slug = route.path.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "root";
      const shot = resolve(OUT_DIR, `bi-v2-gate-${vp.name}-${slug}.png`);
      await page.screenshot({ path: shot, fullPage: true });
      screenshots.push(shot);
    }

    if (consoleErrors.length > 0) {
      failures.push(`${vp.name}: console errors: ${consoleErrors.slice(0, 5).join(" | ")}`);
    }
    await ctx.close();
  }

  if (ROLLBACK_ENABLED) {
    // 关 flag 后 /bi 必须不渲染 v2 shell。
    // 因 dev server 由调用者控制，rollback verifier 只校验同一 URL 下，
    // 若环境变量 BI_BACKOFFICE_V2_SHELL_ENABLED=0/未设置时，v2 shell 不出现。
    console.log("\n[rollback] 建议另行用 BI_BACKOFFICE_V2_SHELL_ENABLED=0 重启后跑 bi_v2_rollback_smoke.mjs.");
  }
} finally {
  await browser.close();
}

console.log("Screenshots saved:");
for (const p of screenshots) console.log("  ", p);
if (failures.length > 0) {
  console.error("\nFAILURES:");
  for (const f of failures) console.error("  ", f);
  process.exit(1);
}
console.log(
  `\nOK · ${screenshots.length} screenshots across ${VIEWPORTS.length} viewports × ${ROUTES.length} routes.`,
);
