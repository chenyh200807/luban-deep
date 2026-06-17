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
          total_feedback: 3,
          thumbs_up: 1,
          thumbs_down: 2,
          neutral: 0,
          commented: 2,
          unique_users: 2,
          unique_sessions: 2,
          unique_messages: 3,
        },
        rating_breakdown: [
          { rating: -1, label: "踩", count: 2 },
          { rating: 1, label: "赞", count: 1 },
        ],
        top_reason_tags: [{ tag: "答非所问", count: 2 }],
        answer_modes: [{ answer_mode: "deep", count: 2 }],
        recent: [],
      }),
    }),
  );
}

async function mockLubanFeedbackReads(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/bi/luban-feedback/stats**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        window_days: 365,
        storage_status: "ok",
        summary: {
          total_responses: 2,
          nps_score: 50,
          nps_base: 2,
          promoters: 1,
          passives: 1,
          detractors: 0,
          avg_satisfaction: 4.5,
          satisfaction_base: 2,
          revisit_willing_count: 1,
          revisit_willing_rate: 0.5,
          with_contact_count: 2,
          with_contact_rate: 1,
        },
        nps_breakdown: [
          { nps: "9", count: 1 },
          { nps: "8", count: 1 },
        ],
        satisfaction_breakdown: [{ overall_satisfaction: "5", count: 1 }],
        most_valuable_breakdown: [{ most_valuable: "case_grading", count: 1 }],
        will_continue_breakdown: [],
        pay_willingness_breakdown: [],
        revisit_willingness_breakdown: [],
        attempt_count_breakdown: [],
        exam_timeframe_breakdown: [],
        status_breakdown: [],
        source_breakdown: [{ source_page: "luban-feedback", count: 2 }],
      }),
    }),
  );
  await page.route("**/api/v1/bi/luban-feedback/responses**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        window_days: 365,
        storage_status: "ok",
        total: 0,
        contact_revealed: true,
        items: [],
      }),
    }),
  );
}

async function mockInviteApplicationApis(
  page: import("@playwright/test").Page,
  capture: {
    patchBody?: Record<string, unknown>;
    deleteBody?: Record<string, unknown>;
    exportBody?: Record<string, unknown>;
    idempotencyKey?: string;
    deleteIdempotencyKey?: string;
    exportIdempotencyKey?: string;
    authorization?: string;
    deleteAuthorization?: string;
    exportAuthorization?: string;
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
        age_range_breakdown: [{ age_range: currentApplication.age_range, count: 1 }],
        province_breakdown: [{ province: currentApplication.province, count: 1 }],
        education_breakdown: [{ education: currentApplication.education, count: 1 }],
        occupation_breakdown: [{ occupation: currentApplication.occupation, count: 1 }],
        preparation_years_breakdown: [
          { preparation_years: currentApplication.preparation_years, count: 1 },
        ],
        knowledge_foundation_breakdown: [
          { knowledge_foundation: currentApplication.knowledge_foundation, count: 1 },
        ],
        daily_study_time_breakdown: [
          { daily_study_time: currentApplication.daily_study_time, count: 1 },
        ],
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
    if (request.method() === "DELETE") {
      capture.deleteIdempotencyKey = request.headers()["x-idempotency-key"];
      capture.deleteAuthorization = request.headers().authorization;
      capture.deleteBody = request.postDataJSON() as Record<string, unknown>;
      currentApplication = { ...currentApplication, status: "archived" };
      return route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          audit_id: "audit_invite_delete_1",
          deduped: false,
          deleted: true,
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
        total: currentApplication.status === "archived" ? 0 : 1,
        contact_revealed: true,
        items: currentApplication.status === "archived" ? [] : [currentApplication],
      }),
    });
  });

  await page.route("**/api/v1/bi/export-jobs", async (route) => {
    const request = route.request();
    capture.exportIdempotencyKey = request.headers()["x-idempotency-key"];
    capture.exportAuthorization = request.headers().authorization;
    capture.exportBody = request.postDataJSON() as Record<string, unknown>;
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        audit_id: "audit_invite_export_1",
        deduped: false,
        export_job: {
          id: "export_audit_invite_export_1",
          name: "内测申请导出",
          dataset: "invite_test_applications",
          format: "csv",
          rows: 0,
          status: "queued",
          scrubbed: true,
          raw_mode: false,
          rate_limit_per_hour: 2,
          requested_at: "2026-06-04T00:00:00Z",
        },
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
  await mockLubanFeedbackReads(page);
  await mockInviteApplicationApis(page, capture);

  await page.goto("/bi?tab=feedback&panel=invite-test");

  await expect(page.getByRole("heading", { name: "内测申请池" })).toBeVisible();
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

test("BI feedback invite-test applications can be deleted through the audited endpoint", async ({
  page,
}) => {
  const capture: {
    deleteBody?: Record<string, unknown>;
    deleteIdempotencyKey?: string;
    deleteAuthorization?: string;
  } = {};

  await installAdminSession(page);
  await mockFeedbackReads(page);
  await mockLubanFeedbackReads(page);
  await mockInviteApplicationApis(page, capture);

  await page.goto("/bi?tab=feedback&panel=invite-test");

  await expect(page.getByText("Codex编辑验证")).toBeVisible();
  await page.getByRole("button", { name: "归档内测申请 app-edit-1" }).click();
  await page.getByRole("button", { name: "确认归档内测申请 app-edit-1" }).click();

  await expect.poll(() => capture.deleteBody?.reason).toBe("admin_deleted_from_bi");
  expect(capture.deleteIdempotencyKey).toBeTruthy();
  expect(capture.deleteAuthorization).toBe(`Bearer ${ADMIN_SESSION.token}`);
  await expect(page.getByText("Codex编辑验证")).toHaveCount(0);
  await expect(page.getByText("暂无内测申请")).toBeVisible();
});

test("BI feedback center macro charts and invite export are visible and audited", async ({
  page,
}) => {
  const capture: {
    exportBody?: Record<string, unknown>;
    exportIdempotencyKey?: string;
    exportAuthorization?: string;
  } = {};

  await installAdminSession(page);
  await mockFeedbackReads(page);
  await mockLubanFeedbackReads(page);
  await mockInviteApplicationApis(page, capture);

  await page.goto("/bi?tab=feedback&panel=invite-test");

  await expect(page.getByRole("heading", { name: "反馈中心全局图表" })).toBeVisible();
  await expect(page.getByText("模块声量占比")).toBeVisible();
  await expect(page.getByText("跟进队列漏斗")).toBeVisible();
  await expect(page.getByText("NPS 结构")).toBeVisible();
  await expect(page.getByText("申请画像汇总")).toBeVisible();
  await expect(page.getByText("年龄占比")).toBeVisible();
  await expect(page.getByText("25-34")).toBeVisible();
  await expect(page.getByText("施工员")).toBeVisible();

  await page.getByRole("button", { name: "导出内测申请 CSV" }).click();

  await expect.poll(() => capture.exportBody?.dataset).toBe("invite_test_applications");
  expect(capture.exportIdempotencyKey).toBeTruthy();
  expect(capture.exportAuthorization).toBe(`Bearer ${ADMIN_SESSION.token}`);
  expect(capture.exportBody).toMatchObject({
    dataset: "invite_test_applications",
    format: "csv",
    filters: {
      days: 365,
      q: "",
      status: "",
      source_page: "",
      visible_rows: 1,
      total: 1,
    },
  });
  await expect(page.getByText("已导出当前筛选全部 1 条；审计 audit_invite_export_1")).toBeVisible();
});
