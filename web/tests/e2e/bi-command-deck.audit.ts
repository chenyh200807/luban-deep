import { expect, test, type Page } from "@playwright/test";

async function mockBiApis(page: Page) {
  await page.route("**/api/v1/bi/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.startsWith("/api/v1/bi/overview")) {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          data: {
            title: "DeepTutor BI 工作台",
            subtitle: "Mock overview",
            cards: [
              { label: "活跃学员", value: 128, delta: "+8%", tone: "good" },
            ],
            highlights: ["成功率最近三个周期持续抬升"],
            entrypoints: [
              { label: "wx_miniprogram", value: 62, rate: 0.73 },
            ],
            alerts: [
              {
                level: "warning",
                title: "成功率波动偏大",
                detail: "过去 7 天有 2 个周期成功率低于 75%",
              },
            ],
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
            items: [
              {
                level: "critical",
                title: "TutorBot 延迟尖峰",
                detail: "04-16 19:00 后延迟高于基线 42%",
              },
            ],
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

    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ data: {} }),
    });
  });
}

async function visitBi(page: Page) {
  await page.goto("/bi");
}

test.describe("BI Command Deck audit", () => {
  test("public bi surface loads without generic workspace fallback", async ({ page }) => {
    await mockBiApis(page);

    await visitBi(page);

    await expect(page).toHaveURL(/\/bi$/);
    await expect(page.getByText("BI workspace unavailable")).toHaveCount(0);
  });

  test("bi deck exposes the new heading", async ({ page }) => {
    await mockBiApis(page);

    await visitBi(page);

    await expect(page.getByRole("heading", { name: "DeepTutor BI Deck" })).toBeVisible();
    await expect(page.getByText("经营、质量、会员、TutorBot 四条主线的一体化指挥舱")).toBeVisible();
  });

  test("bi deck exposes the new primary tabs", async ({ page }) => {
    await mockBiApis(page);

    await visitBi(page);

    await expect(page.getByRole("link", { name: "Overview" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Quality" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Member Ops" })).toBeVisible();
    await expect(page.getByRole("link", { name: "TutorBot" })).toBeVisible();
  });

  test("bi deck removes old in-page anchor navigation", async ({ page }) => {
    await mockBiApis(page);

    await visitBi(page);

    await expect(page.locator('a[href="#trend"]')).toHaveCount(0);
    await expect(page.locator('a[href="#knowledge"]')).toHaveCount(0);
    await expect(page.locator('a[href="#capability"]')).toHaveCount(0);
  });

  test("bi deck opens learner 360 from member samples", async ({ page }) => {
    await mockBiApis(page);

    await visitBi(page);

    await expect(page.getByRole("button", { name: /示例学员 A/ })).toBeVisible();
    await page.getByRole("button", { name: /示例学员 A/ }).click();
    await expect(page.getByRole("heading", { name: "Learner 360" })).toBeVisible();
  });

  test("quality tab renders stability signals from existing BI data", async ({ page }) => {
    await mockBiApis(page);

    await visitBi(page);

    await page.getByRole("link", { name: "Quality" }).click();

    await expect(page).toHaveURL(/\/bi\?tab=quality$/);
    await expect(page.getByText("质量摘要")).toBeVisible();
    await expect(page.getByText("趋势波动")).toBeVisible();
    await expect(page.getByText("TutorBot 延迟尖峰")).toBeVisible();
    await expect(page.getByText("成功率波动偏大")).toBeVisible();
  });
});
