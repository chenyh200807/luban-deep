#!/usr/bin/env node
// Round 3 E — Contract tests with page.route interception.
//
// Smoke screenshots can't catch the regressions that matter most for an
// audit-grade backoffice:
//   1. recordMemberConversationView() commented out → smoke passes, audit
//      silently dropped.
//   2. actor header replaced with literal "ops@deeptutor" → smoke passes.
//   3. X-Idempotency-Key header removed → smoke passes.
//   4. BI_OVERVIEW_V2_ENABLED=true but no /api/v1/bi/overview request → flag
//      becomes a banner-only stub instead of triggering real data fetch.
//
// This script intercepts every /api/v1/* request the browser makes and asserts:
//   - audited writes carry X-Idempotency-Key
//   - audited writes go through Authorization header (proxy for actor binding)
//   - flag-enabled panels actually call their authority endpoints
//
// All assertions are positive; missing required calls fail the smoke. Mock
// responses are returned (no real backend), so the test runs offline.

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { withAdminSession, buildFakeAdminSession } from "./_bi_v2_harness.mjs";

const BASE = process.env.BI_V2_BASE || "http://localhost:3001";
const OUT_DIR = process.env.BI_V2_SHOTS || "/tmp/bi-v2-shots";
mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
const failures = [];
const screenshots = [];

async function withContractContext(handler) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await withAdminSession(ctx);
  const requests = [];
  await ctx.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const body = req.method() === "POST" || req.method() === "PATCH" ? req.postData() : null;
    requests.push({
      url: req.url(),
      method: req.method(),
      headers: req.headers(),
      body,
    });
    // Mock 200 for GETs so panels populate; mock 200 + minimal audit response
    // for POST so reveal path succeeds.
    if (req.method() === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, audit_id: "audit_smoke", undo_token: "smoke_undo" }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ cards: [], alerts: [], points: [], items: [] }),
      });
    }
  });
  const page = await ctx.newPage();
  try {
    await handler(page, requests);
  } finally {
    await ctx.close();
  }
  return requests;
}

// ---------------------------------------------------------------------------
// Contract 1: opening conversation full text must POST view-audit with
// X-Idempotency-Key and Authorization headers. Fails if recordMemberConversationView
// is removed, if useAuditedAction stops injecting idempotency key, or if
// withAdminAuthorization is bypassed.
// ---------------------------------------------------------------------------
const C1_TITLE = "C1 view-audit must include X-Idempotency-Key + Authorization";
{
  const session = buildFakeAdminSession({ token: "contract-token-c1" });
  const requests = await withContractContext.call(
    null,
    async (page, requests) => {
      const ctx = page.context();
      await ctx.addInitScript(
        ({ key, value }) => {
          try {
            window.localStorage.setItem(key, value);
          } catch {}
        },
        {
          key: "deeptutor.bi.admin.session",
          value: JSON.stringify(session),
        },
      );
      await page.goto(`${BASE}/bi?tab=member-ops`, { waitUntil: "domcontentloaded" });
      await page
        .waitForFunction(
          () =>
            document.querySelector("[data-bi-v2-root]")?.getAttribute("data-section") === "member-ops",
          null,
          { timeout: 8000 },
        )
        .catch(() => {});
      await page.locator('button[aria-label^="打开 "][aria-label$="学员 360"]').first().click();
      await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
      await page.locator('button[aria-label="查看会员对话回顾"]').click();
      await page
        .waitForFunction(
          () => document.querySelector('[role="dialog"]')?.textContent?.includes("对话回顾"),
          null,
          { timeout: 5000 },
        )
        .catch(() => {});
      await page.getByRole("radio", { name: "客服投诉" }).check();
      await page.locator('[role="dialog"] button').filter({ hasText: "查看全文" }).first().click();
      await page.waitForTimeout(500);
      const shotPath = resolve(OUT_DIR, "bi-v2-contract-c1-view-audit.png");
      await page.screenshot({ path: shotPath, fullPage: false });
      screenshots.push(shotPath);
    },
  );
  const audit = requests.find(
    (r) => r.url.includes("/conversations/") && r.url.includes("/view-audit") && r.method === "POST",
  );
  if (!audit) {
    failures.push(`${C1_TITLE}: 没有捕获到 view-audit POST (recordMemberConversationView 可能被绕过)`);
  } else {
    if (!audit.headers["x-idempotency-key"]) {
      failures.push(`${C1_TITLE}: 缺 X-Idempotency-Key header (useAuditedAction 被绕过)`);
    }
    if (audit.headers["x-idempotency-key"]?.length < 8) {
      failures.push(`${C1_TITLE}: X-Idempotency-Key 过短 (${audit.headers["x-idempotency-key"]})`);
    }
    if (!audit.headers["authorization"] && !audit.headers["Authorization"]) {
      failures.push(`${C1_TITLE}: 缺 Authorization header (withAdminAuthorization 被绕过)`);
    }
    if (!audit.url.includes("reason=")) {
      failures.push(`${C1_TITLE}: URL 缺 reason= query (审计原因未传给后端)`);
    }
  }
}

// ---------------------------------------------------------------------------
// Contract 2: BI_OVERVIEW_V2_ENABLED=true must trigger a /api/v1/bi/overview
// GET on page load. Fails if BiV2OverviewPanel stops calling loadLive() or
// if the flag becomes a banner-only stub.
// ---------------------------------------------------------------------------
const C2_TITLE = "C2 overview flag enabled must fetch /api/v1/bi/overview";
{
  const session = buildFakeAdminSession({ token: "contract-token-c2" });
  const requests = await withContractContext.call(
    null,
    async (page, _requests) => {
      const ctx = page.context();
      await ctx.addInitScript(
        ({ key, value }) => {
          try {
            window.localStorage.setItem(key, value);
          } catch {}
        },
        {
          key: "deeptutor.bi.admin.session",
          value: JSON.stringify(session),
        },
      );
      await page.goto(`${BASE}/bi`, { waitUntil: "networkidle" });
      await page.waitForTimeout(500);
    },
  );
  const overviewCall = requests.find(
    (r) => r.url.includes("/api/v1/bi/overview") && r.method === "GET",
  );
  if (!overviewCall) {
    failures.push(`${C2_TITLE}: 没有捕获到 /api/v1/bi/overview GET (flag 退化为 banner-only)`);
  }
}

await browser.close();

console.log("Screenshots saved:");
for (const p of screenshots) console.log("  ", p);
if (failures.length > 0) {
  console.error("\nFAILURES:");
  for (const f of failures) console.error("  ", f);
  process.exit(1);
}
console.log("\nOK · 契约测试通过 (audit headers + flag fetch behavior)");
