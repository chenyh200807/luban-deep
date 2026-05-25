import { expect, test } from "@playwright/test";

const ADMIN_SESSION = {
  token: "test-admin-token",
  userId: "admin_test",
  displayName: "QA Admin",
  isAdmin: true,
  expiresAt: 4102444800,
};

const BASE_APPLICATION = {
  id: "app-edit-1",
  created_at: "2026-05-23T10:03:00Z",
  source_page: "invite-test-apply",
  utm_source: "organic",
  utm_campaign: "beta",
  name: "Codex编辑验证",
  phone: "13900005018",
  email: "codex-edit@example.com",
  province: "浙江",
  age_range: "25-34",
  education: "本科",
  occupation: "施工员",
  wechat_id: "wx_codex_edit",
  exam_type: "一建建筑实务",
  exam_stage: "刚开始学建筑实务",
  preparation_years: "1 年",
  knowledge_foundation: "基础薄弱",
  pain_point: "案例题不会写",
  weekly_time: "10-30 分钟",
  daily_study_time: "1 小时",
  current_method: "刷题 + 网课",
  study_difficulties: "不会复盘错题",
  latest_wrong_question: "钢筋保护层题",
  is_yousen_member: "no",
  exam_date: "2026-09-19",
  accept_interview: true,
  consent: true,
  status: "submitted",
  operator_note: "优先回访",
  submit_count: 1,
  contact_revealed: true,
};

async function installAdminSession(page: import("@playwright/test").Page) {
  await page.addInitScript((session) => {
    window.localStorage.setItem("deeptutor.bi.admin.session", JSON.stringify(session));
  }, ADMIN_SESSION);
}

async function mockFeedbackReads(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/bi/feedback**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        window_days: 30,
        storage_status: "ok",
        summary: {
          total_feedback: 0,
          thumbs_up: 0,
          thumbs_down: 0,
          neutral: 0,
          commented: 0,
          unique_users: 0,
          unique_sessions: 0,
          unique_messages: 0,
        },
        rating_breakdown: [],
        top_reason_tags: [],
        answer_modes: [],
        recent: [],
      }),
    }),
  );
}

async function mockInviteApplicationApis(
  page: import("@playwright/test").Page,
  capture: {
    patchBody?: Record<string, unknown>;
    idempotencyKey?: string;
    authorization?: string;
  },
) {
  let currentApplication = { ...BASE_APPLICATION };

  await page.route("**/api/v1/bi/invite-test/stats**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        window_days: 365,
        storage_status: "ok",
        summary: {
          total_applications: 1,
          unique_contacts: 1,
          accept_interview_count: 1,
          accept_interview_rate: 1,
          with_wrong_question_count: 1,
          with_wrong_question_rate: 1,
          consented_count: 1,
        },
        status_breakdown: [{ status: currentApplication.status, count: 1 }],
        source_breakdown: [{ source_page: currentApplication.source_page, count: 1 }],
        exam_type_breakdown: [{ exam_type: currentApplication.exam_type, count: 1 }],
        exam_stage_breakdown: [{ exam_stage: currentApplication.exam_stage, count: 1 }],
        pain_point_breakdown: [{ pain_point: currentApplication.pain_point, count: 1 }],
        weekly_time_breakdown: [{ weekly_time: currentApplication.weekly_time, count: 1 }],
      }),
    }),
  );

  await page.route("**/api/v1/bi/invite-test/applications**", async (route) => {
    const request = route.request();
    if (request.method() === "PATCH") {
      capture.idempotencyKey = request.headers()["x-idempotency-key"];
      capture.authorization = request.headers().authorization;
      capture.patchBody = request.postDataJSON() as Record<string, unknown>;
      currentApplication = { ...currentApplication, ...capture.patchBody };
      return route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          audit_id: "audit_invite_edit_1",
          deduped: false,
          application: currentApplication,
          storage_status: "ok",
        }),
      });
    }

    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        window_days: 365,
        storage_status: "ok",
        total: 1,
        contact_revealed: true,
        items: [currentApplication],
      }),
    });
  });
}

test("BI feedback invite-test applications can be edited through the audited endpoint", async ({
  page,
}) => {
  const capture: {
    patchBody?: Record<string, unknown>;
    idempotencyKey?: string;
    authorization?: string;
  } = {};

  await installAdminSession(page);
  await mockFeedbackReads(page);
  await mockInviteApplicationApis(page, capture);

  await page.goto("/bi?tab=feedback&panel=invite-test");

  await expect(page.getByText("内测申请池")).toBeVisible();
  await expect(page.getByText("Codex编辑验证")).toBeVisible();

  await page.getByRole("button", { name: "编辑内测申请 app-edit-1" }).click();
  const dialog = page.getByRole("dialog", { name: "编辑内测申请 · Codex编辑验证" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("姓名")).toHaveValue("Codex编辑验证");
  await expect(dialog.getByLabel("手机号")).toHaveValue("13900005018");
  await expect(dialog.getByLabel("邮箱")).toHaveValue("codex-edit@example.com");
  await expect(dialog.getByLabel("微信")).toHaveValue("wx_codex_edit");
  await expect(dialog.getByLabel("主要痛点")).toHaveValue("案例题不会写");

  await dialog.getByLabel("状态").selectOption("contacted");
  await dialog.getByLabel("运营备注").fill("已电话联系，安排 5 月 26 日回访");
  await dialog.getByLabel("手机号").fill("13900005019");
  await dialog.getByLabel("每日学习时间").fill("2 小时");

  await dialog.getByRole("button", { name: "保存并审计" }).click();

  await expect.poll(() => capture.patchBody?.status).toBe("contacted");
  expect(capture.idempotencyKey).toBeTruthy();
  expect(capture.authorization).toBe(`Bearer ${ADMIN_SESSION.token}`);
  expect(capture.patchBody).toMatchObject({
    status: "contacted",
    operator_note: "已电话联系，安排 5 月 26 日回访",
    phone: "13900005019",
    daily_study_time: "2 小时",
  });

  await expect(dialog.getByLabel("状态")).toHaveValue("contacted");
  await expect(dialog.getByLabel("手机号")).toHaveValue("13900005019");
});
