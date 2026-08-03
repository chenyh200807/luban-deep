/**
 * 新增注册卡的真组件验收：窗口切换必须真的改变屏幕上的数字。
 *
 * 单测覆盖的是求和逻辑；这里覆盖的是"渲染出来的确实是那个数"——
 * 后端每日序列 → 前端后缀和 → 屏幕大数字这条链路整条走通，
 * 并留下截图供人眼核对（门绿 ≠ 画面对）。
 */
import { expect, test } from "@playwright/test";

const TREND_END_DATE = "2026-06-30";

/**
 * 365 天序列，构造成每个窗口的和唯一可辨：
 *  - 今天(第365天) = 100
 *  - 昨天 = 10，其余近 7 天内每天 = 1（近7天 = 100+10+1*5 = 115）
 *  - 第 8..30 天每天 = 2（近30天 = 115 + 2*23 = 161）
 *  - 第 31..365 天每天 = 0
 */
function buildDailyCounts(): number[] {
  const counts = new Array(365).fill(0);
  counts[364] = 100; // 今天
  counts[363] = 10; // 昨天
  for (let back = 2; back <= 6; back += 1) counts[364 - back] = 1;
  for (let back = 7; back <= 29; back += 1) counts[364 - back] = 2;
  return counts;
}

const DAILY_COUNTS = buildDailyCounts();
const EXPECTED_TODAY = 100;
const EXPECTED_3D = 111;
const EXPECTED_7D = 115;
const EXPECTED_30D = 161;

async function installAdminSession(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "deeptutor.bi.admin.session",
      JSON.stringify({
        token: "test-admin-token",
        userId: "admin_test",
        displayName: "QA Admin",
        isAdmin: true,
        biRole: "bi_admin",
        accessibleTabs: ["member-ops", "learner-360", "audit", "overview"],
        expiresAt: 4102444800,
      }),
    );
  });
}

async function mockMemberOpsOverview(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/bi/member/overview**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dashboard: {
          total_count: 400,
          active_count: 320,
          expiring_soon_count: 4,
          new_today_count: EXPECTED_TODAY,
          new_7d_count: EXPECTED_7D,
          new_30d_count: EXPECTED_30D,
          new_registration_trend: {
            start_date: "2025-07-01",
            end_date: TREND_END_DATE,
            window_days: 365,
            daily_counts: DAILY_COUNTS,
            undated_member_count: 3,
            before_window_member_count: 0,
            future_dated_member_count: 1,
            timezone_offset_minutes: 480,
          },
          churn_risk_count: 7,
          health_score: 80,
          auto_renew_coverage: 12,
          tier_breakdown: [{ tier: "trial", count: 400 }],
          expiry_breakdown: [],
          recommendations: [],
          // 运营口径起点在默认 30 天窗口内 —— 用来验提示只在窗口跨过它时出现。
          authority: { operational_start_at: "2026-06-22T00:00:00+08:00" },
        },
        list: { items: [], total: 0, page: 1, page_size: 20, pages: 1 },
        internal_accounts: { available: true, total_internal: 0 },
        authority: {},
      }),
    }),
  );
  await page.route("**/api/v1/bi/internal-accounts**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ items: [], total_internal: 0, available: true }),
    }),
  );
}

test("新增注册卡：1/3/7/30 天可点击切换并改变屏幕数字", async ({ page }) => {
  await installAdminSession(page);
  await mockMemberOpsOverview(page);

  await page.goto("/bi?tab=member-ops");

  const card = page.getByTestId("bi-member-new-registration-card");
  await expect(card).toBeVisible({ timeout: 30_000 });

  const total = page.getByTestId("bi-member-new-registration-total");
  const windowSelect = page.getByTestId("bi-member-new-registration-window");

  // 默认近 30 天：窗口起点 2026-06-01 早于运营口径起点 2026-06-22 → 必须提示
  await expect(windowSelect).toHaveValue("30");
  await expect(windowSelect.locator("option")).toHaveText([
    "近 1 天",
    "近 3 天",
    "近 7 天",
    "近 30 天",
  ]);
  // 必须走一次真实指针命中；selectOption 会绕过遮挡层，抓不到“看得见但点不开”。
  await windowSelect.click();
  await page.keyboard.press("Escape");
  await expect(total).toHaveText(EXPECTED_30D.toLocaleString());
  await expect(card).toContainText("注册时间缺失或异常");
  await expect(page.getByTestId("bi-member-new-registration-predates-note")).toContainText(
    "2026-06-22",
  );

  // 窗口收到今日（起点 2026-06-30 晚于口径起点）→ 提示必须消失，不能常驻噪音
  await windowSelect.selectOption("1");
  await expect(page.getByTestId("bi-member-new-registration-predates-note")).toHaveCount(0);
  await windowSelect.selectOption("30");
  await page.screenshot({
    path: "playwright-report/new-registration-30d.png",
    fullPage: false,
  });

  // 切近 7 天
  await windowSelect.selectOption("7");
  await expect(total).toHaveText(EXPECTED_7D.toLocaleString());

  // 鼠标移到具体日期：即时显示完整日期 + 当日人数，不能只依赖浏览器延迟 title。
  const firstDailyBar = page.getByTestId("bi-member-new-registration-bar-0");
  const tooltip = page.getByTestId("bi-member-new-registration-tooltip");
  await firstDailyBar.hover();
  await expect(tooltip).toHaveAttribute("aria-hidden", "false");
  await expect(tooltip).toContainText("2026年6月24日");
  await expect(tooltip).toContainText("1 人");
  await expect(tooltip).toHaveCSS("opacity", "1");
  await page.screenshot({
    path: "playwright-report/new-registration-hover.png",
    fullPage: false,
  });

  // 键盘用户聚焦同一柱时获得同样的具体数字。
  await firstDailyBar.focus();
  await expect(firstDailyBar).toHaveAttribute("aria-label", "2026年6月24日，1 人");
  await expect(tooltip).toHaveAttribute("aria-hidden", "false");

  // 切近 3 天
  await windowSelect.selectOption("3");
  await expect(total).toHaveText(EXPECTED_3D.toLocaleString());

  // 切今日
  await windowSelect.selectOption("1");
  await expect(total).toHaveText(EXPECTED_TODAY.toLocaleString());
  // 今日的上一周期是昨天(10)，环比 100 vs 10 = +900%
  await expect(page.getByTestId("bi-member-new-registration-delta")).toContainText("900%");

  await windowSelect.selectOption("3");
  await expect(total).toHaveText(EXPECTED_3D.toLocaleString());
  await page.screenshot({
    path: "playwright-report/new-registration-3d.png",
    fullPage: false,
  });
});

test("新增注册序列缺失时显示空态，不拿旧字段伪造数字", async ({ page }) => {
  await installAdminSession(page);
  await page.route("**/api/v1/bi/member/overview**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dashboard: {
          total_count: 400,
          active_count: 320,
          expiring_soon_count: 4,
          new_today_count: 9,
          new_7d_count: 99,
          new_30d_count: 999,
          churn_risk_count: 7,
          health_score: 80,
          auto_renew_coverage: 12,
          tier_breakdown: [],
          expiry_breakdown: [],
          recommendations: [],
        },
        list: { items: [], total: 0, page: 1, page_size: 20, pages: 1 },
        internal_accounts: { available: true, total_internal: 0 },
        authority: {},
      }),
    }),
  );

  await page.goto("/bi?tab=member-ops");

  const card = page.getByTestId("bi-member-new-registration-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toContainText("新增注册序列不可用");
  await expect(page.getByTestId("bi-member-new-registration-total")).toHaveCount(0);
  // 旧的 new_*_count 绝不能被当成窗口值渲染出来
  await expect(card).not.toContainText("999");
});
