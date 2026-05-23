#!/usr/bin/env node
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { withAdminSession } from "./_bi_v2_harness.mjs";

const BASE = process.env.BI_V2_BASE || "http://localhost:3001";
const OUT_DIR = process.env.BI_V2_SHOTS || "/tmp/bi-v2-shots";
mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
const failures = [];
const screenshots = [];

try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  // Round 3 C: panel hidden behind RequireBiAdmin — inject fake admin session.
  await withAdminSession(ctx);
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const text = m.text();
    if (/Failed to load resource: the server responded with a status of (4\d\d|5\d\d)/.test(text)) return;
    if (text.includes("/api/v1/bi/")) return;
    consoleErrors.push(text);
  });
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));

  await page.goto(`${BASE}/bi`, { waitUntil: "networkidle", timeout: 60000 });
  await page.evaluate(() => { window.location.hash = "member-ops"; });
  await page.waitForFunction(() => document.querySelector("[data-bi-v2-root]")?.getAttribute("data-section") === "member-ops");
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

  // 验证 7 默认列
  const headerCells = await page.evaluate(() =>
    Array.from(document.querySelectorAll("table thead th")).map((th) => th.textContent?.trim()),
  );
  const dataHeaders = headerCells.filter(
    (h) => h && !["", "动作"].includes(h),
  );
  if (dataHeaders.length < 7) {
    failures.push(`默认列数 = ${dataHeaders.length}, 期望 ≥ 7. cells=${JSON.stringify(headerCells)}`);
  }

  // 打开 360 抽屉
  const open360Btn = page.locator('button[aria-label^="打开 "][aria-label$="学员 360"]').first();
  const btnCount = await open360Btn.count();
  if (btnCount === 0) {
    failures.push("找不到 360 抽屉触发按钮 (button[aria-label*='学员 360'])");
  } else {
    await open360Btn.click();
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
  }
  const drawerTitle = await page.evaluate(() => document.querySelector('[role="dialog"]')?.textContent?.slice(0, 50));
  if (!drawerTitle?.includes("学员 360")) {
    failures.push(`360 抽屉 title 缺失: ${drawerTitle}`);
  }
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  const drawerShot = resolve(OUT_DIR, "bi-v2-crm-360-drawer.png");
  await page.screenshot({ path: drawerShot, fullPage: false });
  screenshots.push(drawerShot);

  // 进入对话回顾
  await page.getByRole("button", { name: /查看会员对话回顾/ }).click();
  await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.textContent?.includes("对话回顾"), null, { timeout: 5000 });

  // 全文按钮初始应禁用
  const fullBtnInitiallyDisabled = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('[role="dialog"] button')).filter(
      (b) => b.textContent?.includes("查看全文"),
    );
    return btns.length > 0 && btns.every((b) => b.hasAttribute("disabled"));
  });
  if (!fullBtnInitiallyDisabled) {
    failures.push("对话全文按钮未在无原因时禁用（破坏审计契约）");
  }

  // 选择原因 (计划要求 6 种之一，这里用第一项"客服投诉")
  await page.getByRole("radio", { name: "客服投诉" }).check();
  // 选原因后按钮应启用 (admin 已通过 RequireBiAdmin)
  const fullBtnEnabled = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('[role="dialog"] button')).filter(
      (b) => b.textContent?.includes("查看全文"),
    );
    return btns.length > 0 && btns.some((b) => !b.hasAttribute("disabled"));
  });
  if (!fullBtnEnabled) {
    failures.push("选原因后对话全文按钮未启用");
  }
  // 点击全文 — 后端 require_admin 会拒绝 smoke 的假 token (401)。
  // 审计契约要求：fetch 失败时 expandedId 不被设置，全文不渲染，audit denied banner 出现。
  await page.locator('[role="dialog"] button').filter({ hasText: "查看全文" }).first().click();
  // 等待 audit 状态从 writing 转为 denied (服务端 401)
  await page
    .waitForFunction(
      () => document.body.textContent?.includes("audit 未写入服务端") ?? false,
      null,
      { timeout: 10000 },
    )
    .catch(() => {});
  const auditDeniedBannerVisible = await page.evaluate(() =>
    document.body.textContent?.includes("audit 未写入服务端"),
  );
  if (!auditDeniedBannerVisible) {
    failures.push("audit denied banner 未显示（后端 401 时应阻止 reveal）");
  }
  const fullContentLeaked = await page.evaluate(() =>
    document.body.textContent?.includes("[全文按需加载占位"),
  );
  if (fullContentLeaked) {
    failures.push("audit 失败时全文仍展开（破坏审计契约：fetch 失败必须阻止 reveal）");
  }
  const auditShot = resolve(OUT_DIR, "bi-v2-crm-conversation-audit-denied.png");
  await page.screenshot({ path: auditShot, fullPage: false });
  screenshots.push(auditShot);

  // Esc 关闭对话回顾抽屉 (应弹回 360，对话标题消失)
  await page.locator('[role="dialog"]').focus();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const dialogTextAfterEsc1 = await page.evaluate(
    () => document.querySelector('[role="dialog"]')?.textContent?.slice(0, 40) ?? "",
  );
  if (dialogTextAfterEsc1.includes("对话回顾")) {
    failures.push(`Esc 未关闭对话回顾抽屉（仍显示 ${dialogTextAfterEsc1}）`);
  }
  // 再次 Esc 应关闭 360
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const lingeringDialog = await page.evaluate(() => Boolean(document.querySelector('[role="dialog"]')));
  if (lingeringDialog) {
    failures.push("第二次 Esc 未关闭学员 360 抽屉");
  }

  if (consoleErrors.length > 0) {
    failures.push(`console errors: ${consoleErrors.slice(0, 5).join(" | ")}`);
  }

  await ctx.close();
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
console.log("\nOK · CRM 抽屉与对话审计交互通过");
