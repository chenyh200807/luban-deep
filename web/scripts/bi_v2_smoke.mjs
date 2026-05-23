#!/usr/bin/env node
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

const SECTIONS = ["overview", "member-ops", "commerce", "feedback", "ops"];

async function run() {
  const browser = await chromium.launch();
  const failures = [];
  const screenshots = [];

  try {
    for (const vp of VIEWPORTS) {
      const ctx = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });
      // Round 3 C: panels live behind RequireBiAdmin — must inject fake admin
      // session before any page.goto otherwise we only see the login prompt.
      await withAdminSession(ctx);
      const page = await ctx.newPage();
      const consoleErrors = [];
      page.on("console", (msg) => {
        if (msg.type() !== "error") return;
        const text = msg.text();
        // Tolerate API fallback errors — overview v2 explicitly shows a banner when
        // backend overview/active-trend/anomalies return 4xx/5xx (e.g. dev without admin session).
        if (/Failed to load resource: the server responded with a status of (4\d\d|5\d\d)/.test(text)) return;
        if (text.includes("/api/v1/bi/")) return;
        consoleErrors.push(text);
      });
      page.on("pageerror", (err) => {
        consoleErrors.push(`pageerror: ${err.message}`);
      });

      const url = `${BASE}/bi`;
      const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
      if (!resp || resp.status() >= 400) {
        failures.push(`${vp.name}: initial HTTP ${resp?.status() ?? "no-response"}`);
        await ctx.close();
        continue;
      }
      const root = page.locator("[data-bi-v2-root]").first();
      await root.waitFor({ state: "attached", timeout: 8000 }).catch(() => {});
      const rootCount = await root.count();
      if (rootCount === 0) {
        const shotPath = resolve(OUT_DIR, `bi-v2-${vp.name}-legacy.png`);
        await page.screenshot({ path: shotPath, fullPage: true });
        screenshots.push(shotPath);
        failures.push(
          `${vp.name}: BI v2 shell not rendered (set BI_BACKOFFICE_V2_SHELL_ENABLED=1 to enable). legacy screenshot: ${shotPath}`,
        );
        await ctx.close();
        continue;
      }

      await page.waitForLoadState("networkidle", { timeout: 30000 });
      for (const section of SECTIONS) {
        await page.evaluate((s) => {
          window.location.hash = s;
        }, section);
        await page.waitForFunction(
          (expected) => {
            const root = document.querySelector("[data-bi-v2-root]");
            if (root?.getAttribute("data-section") !== expected) return false;
            const labelMap = {
              overview: "经营总览",
              "member-ops": "会员运营",
              commerce: "商品账务",
              feedback: "反馈中心",
              ops: "系统运维",
            };
            const activeBtn = document.querySelector('nav button[aria-current="page"]');
            return Boolean(activeBtn && activeBtn.textContent?.includes(labelMap[expected]));
          },
          section,
          { timeout: 5000 },
        );
        const horizontal = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        if (horizontal > 1) {
          failures.push(`${vp.name} ${section}: horizontal overflow ${horizontal}px`);
        }
        // wait for paint flush so sidebar active highlight matches DOM aria-current
        await page.evaluate(
          () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
        );
        const shotPath = resolve(OUT_DIR, `bi-v2-${vp.name}-${section}.png`);
        await page.screenshot({ path: shotPath, fullPage: true });
        screenshots.push(shotPath);
      }

      if (consoleErrors.length > 0) {
        failures.push(`${vp.name}: console errors: ${consoleErrors.slice(0, 3).join(" | ")}`);
      }
      await ctx.close();
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
    `\nOK · ${screenshots.length} screenshots across ${VIEWPORTS.length} viewports × ${SECTIONS.length} sections.`,
  );
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
