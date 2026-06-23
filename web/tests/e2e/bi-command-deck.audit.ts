import { expect, test, type Page } from "@playwright/test";

type MockBiApisOptions = {
  overviewAlerts?: Array<{ level: string; title: string; detail?: string }>;
  anomalyItems?: Array<{ level: string; title: string; detail?: string }>;
};

async function installAdminSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "deeptutor.bi.admin.session",
      JSON.stringify({
        token: "test-admin-token",
        userId: "admin_test",
        displayName: "Admin Test",
        isAdmin: true,
        expiresAt: Math.floor(Date.now() / 1000) + 3600,
      })
    );
  });
}

async function mockBiApis(page: Page, options: MockBiApisOptions = {}) {
  const overviewAlerts = options.overviewAlerts ?? [
    {
      level: "warning",
      title: "成功率波动偏大",
      detail: "过去 7 天有 2 个周期成功率低于 75%",
    },
  ];
  const anomalyItems = options.anomalyItems ?? [
    {
      level: "critical",
      title: "TutorBot 延迟尖峰",
      detail: "04-16 19:00 后延迟高于基线 42%",
    },
  ];

  await page.route("**/api/v1/auth/profile", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        user_id: "admin_test",
        display_name: "Admin Test",
        is_admin: true,
        data: {
          user: {
            user_id: "admin_test",
            display_name: "Admin Test",
            is_admin: true,
          },
        },
      }),
    });
  });

  await page.route("**/api/v1/bi/member/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const memberListItem = {
      user_id: "learner-001",
      display_name: "示例学员 A",
      phone: "13900000001",
      tier: "vip",
      status: "active",
      segment: "exam-prep",
      risk_level: "low",
      auto_renew: true,
      expire_at: "2026-12-31T00:00:00.000Z",
      created_at: "2026-04-01T00:00:00.000Z",
      last_active_at: "2026-04-20T08:00:00.000Z",
      points_balance: 88,
      review_due: 2,
    };

    if (path === "/api/v1/bi/member/list") {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          items: [memberListItem],
          total: 1,
          page: 1,
          page_size: 20,
          pages: 1,
        }),
      });
      return;
    }

    if (path === "/api/v1/bi/member/dashboard") {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          total_count: 1,
          active_count: 1,
          expiring_soon_count: 0,
          new_today_count: 0,
          new_7d_count: 0,
          new_30d_count: 0,
          churn_risk_count: 0,
          health_score: 96,
          auto_renew_coverage: 1,
          tier_breakdown: [{ tier: "vip", count: 1 }],
          expiry_breakdown: [{ label: "稳定", count: 1 }],
          recommendations: [],
        }),
      });
      return;
    }

    if (path === "/api/v1/bi/member/learner-001/360") {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ...memberListItem,
          wallet: {
            balance: 88,
            packages: [],
          },
          study_days: 12,
          focus_topic: "案例题",
          focus_query: "钢筋保护层",
          exam_date: "2026-09-19",
          daily_target: 30,
          difficulty_preference: "medium",
          explanation_style: "deep",
          review_reminder: true,
          earned_badge_ids: [],
          chapter_mastery: {
            chapter_1: { name: "建筑实务", mastery: 0.78 },
          },
          recent_notes: [],
          recent_ledger: [],
          recent_conversations: [],
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
  });

  await page.route("**/api/v1/observability/launch-readiness", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ data: { checks: [], summary: {} } }),
    });
  });

  await page.route("**/api/v1/bi/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.startsWith("/api/v1/bi/overview")) {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          data: {
            title: "鲁班智考 BI 工作台",
            subtitle: "Mock overview",
            cards: [
              { label: "活跃学员", value: 128, delta: "+8%", tone: "good" },
            ],
            highlights: ["成功率最近三个周期持续抬升"],
            entrypoints: [
              { label: "wx_miniprogram", value: 62, rate: 0.73 },
            ],
            alerts: overviewAlerts,
          },
        }),
      });
      return;
    }

    if (path.startsWith("/api/v1/bi/active-trend")) {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          data: {
            points: [
              { label: "04-14", active: 92, cost: 320, successful: 0.82 },
              { label: "04-15", active: 104, cost: 348, successful: 0.79 },
              { label: "04-16", active: 110, cost: 372, successful: 0.76 },
              { label: "04-17", active: 121, cost: 395, successful: 0.88 },
            ],
          },
        }),
      });
      return;
    }

    if (path.startsWith("/api/v1/bi/anomalies")) {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          data: {
            items: anomalyItems,
          },
        }),
      });
      return;
    }

    if (path.startsWith("/api/v1/bi/members")) {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          data: {
            samples: [
              {
                user_id: "learner-001",
                display_name: "示例学员 A",
                tier: "vip",
                risk_level: "low",
                last_active_at: "2026-04-20T08:00:00.000Z",
                detail: "会员样本入口",
              },
            ],
          },
        }),
      });
      return;
    }

    if (path.startsWith("/api/v1/bi/learner/")) {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          data: {
            user_id: "learner-001",
            display_name: "示例学员 A",
            profile: [
              { label: "活跃天数", value: 12 },
            ],
            recent_sessions: [],
            chapter_mastery: [],
            notes_summary: {
              notes_count: 2,
              pinned_notes_count: 1,
              wallet_balance: 88,
              summary: "Learner 360 mock detail",
            },
          },
        }),
      });
      return;
    }

    if (path.startsWith("/api/v1/bi/cost/reconciliation")) {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          data: {
            providers: {
              deepseek: {
                internal: {
                  status: "ok",
                  total_tokens: 1600,
                  currency_amounts: { USD: 0.0001 },
                },
                official_usage: {
                  status: "unconfigured",
                  currency_amounts: {},
                },
                reconciliation: {
                  status: "waiting_for_official_export",
                  token_delta: 1600,
                  warnings: ["waiting_for_official_export"],
                },
              },
              dashscope: {
                internal: {
                  status: "ok",
                  total_tokens: 2200,
                  currency_amounts: { CNY: 0.08 },
                },
                official_usage: {
                  status: "ok",
                  total_tokens: 2000,
                  list_price_cost: { CNY: 0.1 },
                  net_charge_cost: { CNY: 0.07 },
                },
                reconciliation: {
                  status: "warning",
                  token_delta: 200,
                  amount_delta_by_currency: { CNY: -0.02 },
                  warnings: ["amount_delta"],
                },
              },
            },
          },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ data: {} }),
    });
  });
}

async function visitBi(page: Page, path = "/bi") {
  await page.goto(path, { waitUntil: "commit" });
  await expect(page).toHaveURL(/\/bi(?:\?.*)?$/);
}

test.describe("BI Command Deck audit", () => {
  test.describe.configure({ timeout: 90000 });

  test("bi deck renders the standard command surface and drilldowns", async ({ page }) => {
    await installAdminSession(page);
    await mockBiApis(page);

    await visitBi(page);

    await expect(page.getByText("BI workspace unavailable")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "鲁班智考 BI 工作台" })).toBeVisible();
    await expect(page.getByText("COMMAND DECK SHELL")).toHaveCount(0);
    await expect(
      page
        .getByRole("main")
        .getByText("经营、质量、会员、TutorBot 四条主线的轻量总览入口。")
        .first()
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "老板工作台" })).toBeVisible();
    await expect(page.getByRole("link", { name: "会员运营" })).toBeVisible();
    await expect(page.getByRole("link", { name: "上线面板" })).toBeVisible();
    await expect(page.getByRole("link", { name: "内测申请" })).toBeVisible();
    await expect(page.getByRole("link", { name: "内测回访" })).toBeVisible();
    await expect(page.getByRole("link", { name: "学员 360" })).toBeVisible();
    await expect(page.getByRole("link", { name: "经营审计" })).toBeVisible();
    await expect(page.locator('a[href="#trend"]')).toHaveCount(0);
    await expect(page.locator('a[href="#knowledge"]')).toHaveCount(0);
    await expect(page.locator('a[href="#capability"]')).toHaveCount(0);

    await expect(page.getByRole("heading", { name: "主趋势图" }).first()).toBeVisible();
    await expect(page.getByText("右侧混合待处理区").first()).toBeVisible();
    await expect(page.getByText("TutorBot 延迟尖峰")).toBeVisible();
    await expect(page.getByText("成功率最近三个周期持续抬升").first()).toBeVisible();

    const chart = page.locator("svg").filter({
      has: page.locator('path[stroke="#6d28d9"]'),
    }).first();

    await expect(chart.locator('path[stroke="#6d28d9"]')).toHaveCount(1);
    await expect(chart.locator('path[stroke="#0f766e"]')).toHaveCount(1);
    await expect(chart.locator('path[stroke="#C35A2C"]')).toHaveCount(1);

    await expect(page.getByRole("heading", { name: "官方账单对账" })).toBeVisible();
    await expect(page.getByText("DeepSeek 官方")).toBeVisible();
    await expect(page.getByText("unconfigured", { exact: true })).toBeVisible();
    await expect(page.getByText("阿里云 DashScope/Bailian")).toBeVisible();

    await expect(page.getByRole("button", { name: /示例学员 A/ })).toBeVisible();
    await page.getByRole("button", { name: /示例学员 A/ }).click();
    await expect(page.getByText("LEARNER 360")).toBeVisible();
    await expect(page.getByRole("heading", { name: "示例学员 A" })).toBeVisible();

    await page.getByRole("link", { name: "会员运营" }).click();

    await expect(page.getByRole("heading", { name: "会员运营" })).toBeVisible();
    await expect(page.getByText("当前列表")).toBeVisible();
    await expect(page.getByText("工作区状态")).toBeVisible();
    await expect(page.getByRole("button", { name: /示例学员 A/ })).toBeVisible();
    await expect(page.getByText("COMMAND DECK SHELL")).toHaveCount(0);
  });

  test("quality tab treats empty alert feeds as complete data instead of missing data", async ({ page }) => {
    await installAdminSession(page);
    await mockBiApis(page, { overviewAlerts: [], anomalyItems: [] });

    await visitBi(page);

    await expect(page.getByText("当前为空 · 待补齐")).toHaveCount(0);
    await expect(page.getByText("当前没有混合待处理项，空队列不视为异常。").first()).toBeVisible();
  });
});
