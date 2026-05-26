import { expect, test } from "@playwright/test";

async function installAdminSession(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "deeptutor.bi.admin.session",
      JSON.stringify({
        token: "test-admin-token",
        userId: "admin_test",
        displayName: "QA Admin",
        isAdmin: true,
        expiresAt: 4102444800,
      }),
    );
  });
}

async function mockBiV2ReadApis(
  page: import("@playwright/test").Page,
  options: {
    onFeedbackTriage?: (idempotencyKey: string) => void;
    onExportRequest?: (idempotencyKey: string) => void;
  } = {},
) {
  await page.route("**/api/v1/bi/overview**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        cards: [
          {
            label: "活跃学习会话",
            value: 56,
            hint: "近 30 天窗口",
            delta: "+6%",
            tone: "good",
          },
        ],
        alerts: [
          {
            level: "warning",
            title: "AI 反馈 negative 24h 增加",
            detail: "FeedbackService.list / quality",
          },
        ],
      }),
    }),
  );
  await page.route("**/api/v1/bi/active-trend**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        points: [{ label: "Day 1", active: 10, cost: 1, successful: 8 }],
      }),
    }),
  );
  await page.route("**/api/v1/bi/anomalies**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ items: [] }),
    }),
  );
  await page.route("**/api/v1/bi/feedback**", (route) => {
    if (route.request().method() === "POST") {
      options.onFeedbackTriage?.(route.request().headers()["x-idempotency-key"] ?? "");
      return route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          audit_id: "audit_feedback_1",
          deduped: false,
          status: "triaged",
          feedback: {
            feedback_id: "fb_test_1",
            id: "fb_test_1",
            user_id: "user_1",
            session_id: "session_1",
            message_id: "msg_1",
            rating: -1,
            reason_tags: ["答非所问"],
            comment: "学员反馈讲解不清楚",
            feedback_source: "ai_message",
            triage_status: "triaged",
            triage_operator: "admin_test",
            triage_note: "BI feedback triage",
            created_at: "2026-05-23T10:00:00Z",
          },
        }),
      });
    }
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        window_days: 30,
        storage_status: "ok",
        summary: {
          total_feedback: 1,
          thumbs_up: 0,
          thumbs_down: 1,
          neutral: 0,
          commented: 1,
          unique_users: 1,
          unique_sessions: 1,
          unique_messages: 1,
        },
        rating_breakdown: [],
        top_reason_tags: [],
        answer_modes: [],
        recent: [
          {
            feedback_id: "fb_test_1",
            user_id: "user_1",
            session_id: "session_1",
            message_id: "msg_1",
            rating: -1,
            reason_tags: ["答非所问"],
            comment: "学员反馈讲解不清楚",
            feedback_source: "ai_message",
            answer_mode: "deep",
            effective_response_mode: "deep",
            problem_type: "learning_report",
            symptom_tags: ["data_wrong", "card_tap_failed"],
            attachment_count: 1,
            attachments: [
              {
                id: "fb-att-1",
                kind: "image",
                filename: "screen.png",
                mime_type: "image/png",
                size: 2048,
                url: "/api/attachments/feedback-user_1/fb-att-1/screen.png",
              },
            ],
            context_snapshot: {
              route: "packageDeeptutor/pages/profile/profile",
              network_type: "wifi",
              device_model: "iPhone",
              system: "iOS 17",
            },
            created_at: "2026-05-23T10:00:00Z",
          },
        ],
      }),
    });
  });
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
        status_breakdown: [{ status: "submitted", count: 1 }],
        source_breakdown: [{ source_page: "/invite-test/apply", count: 1 }],
        exam_type_breakdown: [{ exam_type: "一建实务", count: 1 }],
        exam_stage_breakdown: [{ exam_stage: "冲刺", count: 1 }],
        pain_point_breakdown: [{ pain_point: "想要错题讲评", count: 1 }],
        weekly_time_breakdown: [{ weekly_time: "5 小时以上", count: 1 }],
      }),
    }),
  );
  await page.route("**/api/v1/bi/invite-test/applications**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        window_days: 365,
        storage_status: "ok",
        total: 1,
        contact_revealed: true,
        items: [
          {
            id: "invite_1",
            created_at: "2026-05-23T10:03:00Z",
            source_page: "/invite-test/apply",
            utm_source: "organic",
            utm_campaign: "beta",
            name: "张同学",
            phone: "13900000001",
            email: "zhang@example.com",
            province: "浙江",
            age_range: "25-34",
            education: "本科",
            occupation: "施工员",
            wechat_id: "wx_zhang",
            exam_type: "一建实务",
            exam_stage: "冲刺",
            preparation_years: "1 年",
            knowledge_foundation: "基础薄弱",
            pain_point: "想要错题讲评",
            weekly_time: "5 小时以上",
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
          },
        ],
      }),
    }),
  );
  await page.route("**/api/v1/bi/commerce**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        status: "ready",
        summary: {
          member_count: 1,
          package_count: 1,
          recharge_count: 1,
          ledger_count: 2,
          anomaly_count: 1,
          credit_points: 1200,
          debit_points: 20,
        },
        authority: {
          packages: "member_console.packages",
          recharge_records: "wallet_ledger",
          wallet_ledger: "wallet_ledger",
          orders: "pending_payment_order_authority",
          anomalies: "bi_service.commerce_rules",
        },
        packages: [
          {
            id: "advance",
            name: "精学版",
            tier: "vip",
            points: 4400,
            price_cny: 99,
            features: ["每周稳定学习额度", "适合错题讲解"],
            status: "active",
            authority: "member_console.packages",
            trust: "C",
          },
        ],
        recharge_records: [
          {
            id: "ord_real_1",
            user_id: "user_1",
            points: 1200,
            amount_cny: 99,
            channel: "wechat",
            status: "confirmed",
            created_at: "2026-05-23T10:00:00+08:00",
            ledger_event_id: "ledger_real_1",
            idempotency_key: "order:ord_real_1",
            authority: "wallet_ledger",
            trust: "A",
          },
        ],
        ledger: [
          {
            id: "ledger_real_1",
            user_id: "user_1",
            kind: "credit",
            event_type: "grant",
            amount: 1200,
            balance_after: 1320,
            reference_type: "order",
            reference_id: "ord_real_1",
            idempotency_key: "order:ord_real_1",
            effective_at: "2026-05-23T10:00:00+08:00",
            metadata: { channel: "wechat", amount_cny: 99 },
            authority: "wallet_ledger",
            trust: "A",
          },
          {
            id: "ledger_real_2",
            user_id: "user_1",
            kind: "debit",
            event_type: "usage",
            amount: -20,
            balance_after: 1300,
            reference_type: "usage",
            reference_id: "session_1",
            idempotency_key: "usage:session_1",
            effective_at: "2026-05-23T11:00:00+08:00",
            metadata: { capability: "deep_solve" },
            authority: "wallet_ledger",
            trust: "A",
          },
        ],
        anomalies: [
          {
            rule_id: "WALLET_CREDIT_WITHOUT_ORDER_AUTHORITY",
            severity: "medium",
            detected_at: "实时",
            affected: 1,
            owner: "finance",
            status: "triaged",
            trust: "B",
            description: "存在入账记录但无法关联订单 authority。",
          },
        ],
        warnings: [],
      }),
    }),
  );
  await page.route("**/api/v1/bi/export-jobs", (route) => {
    options.onExportRequest?.(route.request().headers()["x-idempotency-key"] ?? "");
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        audit_id: "audit_export_1",
        deduped: false,
        export_job: {
          id: "export_audit_export_1",
          name: "操作审计导出",
          dataset: "member_audit_log",
          format: "csv",
          rows: 0,
          status: "queued",
          scrubbed: true,
          rate_limit_per_hour: 2,
          requested_at: "2026-05-23T10:05:00Z",
        },
      }),
    });
  });
  await page.route("**/api/v1/member/audit-log**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        items: [
          {
            id: "audit_1",
            operator: "admin_test",
            action: "member.conversation.view_full",
            target_user: "user_1/session_1",
            reason: "客服投诉",
            created_at: "2026-05-23T10:02:00Z",
            before: { expanded: false },
            after: { expanded: true },
          },
        ],
        total: 1,
        page: 1,
        page_size: 100,
        pages: 1,
      }),
    }),
  );
}

async function mockMemberOpsApis(
  page: import("@playwright/test").Page,
  options: { onMemberOpsAction?: (idempotencyKey: string) => void; memberCount?: number } = {},
) {
  const memberItems = Array.from({ length: options.memberCount ?? 1 }, (_, index) => {
    const phone = index === 0 ? "13900000001" : `1390000${String(index + 1).padStart(4, "0")}`;
    return {
      user_id: index === 0 ? "user_1" : `user_${index + 1}`,
      display_name: index === 0 ? "测试会员" : `测试会员 ${index + 1}`,
      phone,
      tier: "trial",
      status: "active",
      segment: "trial",
      risk_level: "low",
      auto_renew: false,
      expire_at: "2026-06-01T00:00:00+08:00",
      created_at: "2026-05-01T00:00:00+08:00",
      last_active_at: "2026-05-23T10:00:00+08:00",
      points_balance: 120,
      review_due: 0,
    };
  });

  await page.route("**/api/v1/member/dashboard**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        total_count: memberItems.length,
        active_count: memberItems.length,
        expiring_soon_count: 0,
        new_today_count: 0,
        churn_risk_count: 0,
        health_score: 92,
        auto_renew_coverage: 0,
        tier_breakdown: [{ tier: "trial", count: 1 }],
        expiry_breakdown: [],
        recommendations: [],
      }),
    }),
  );
  await page.route("**/api/v1/member/list**", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        items: memberItems,
        total: memberItems.length,
        page: 1,
        page_size: 100,
        pages: 1,
      }),
    }),
  );
  await page.route("**/api/v1/member/user_1/360", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        user_id: "user_1",
        display_name: "测试会员",
        phone: "13900000001",
        tier: "trial",
        status: "active",
        segment: "trial",
        risk_level: "low",
        auto_renew: false,
        expire_at: "2026-06-01T00:00:00+08:00",
        created_at: "2026-05-01T00:00:00+08:00",
        last_active_at: "2026-05-23T10:00:00+08:00",
        wallet: { balance: 120, packages: [] },
        study_days: 3,
        review_due: 0,
        focus_topic: "地基基础",
        focus_query: "怎么复习地基基础",
        exam_date: "2026-09-19",
        daily_target: 30,
        difficulty_preference: "medium",
        explanation_style: "detailed",
        review_reminder: true,
        earned_badge_ids: [],
        chapter_mastery: {},
        recent_notes: [],
        recent_ledger: [],
        recent_conversations: [],
        learner_state: null,
        heartbeat: { jobs: [], history: [], arbitration_history: [] },
        bot_overlays: [],
      }),
    }),
  );
  await page.route("**/api/v1/bi/member/user_1/ops-action", (route) => {
    options.onMemberOpsAction?.(route.request().headers()["x-idempotency-key"] ?? "");
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        status: "done",
        result: "BI 标记已联系",
        action_title: "标记已联系",
        next_follow_up_at: "",
        audit_id: "audit_member_action_1",
        deduped: false,
        note: { id: "note_ops_1", channel: "ops_action" },
      }),
    });
  });
  await page.route("**/api/v1/member/user_1/conversations**", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          session_id: "session_1",
          title: "地基基础答疑",
          message_count: 2,
          capability: "chat",
          audit_id: "audit_test",
        }),
      });
    }
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        user_id: "user_1",
        total: 1,
        items: [
          {
            session_id: "session_1",
            title: "地基基础答疑",
            updated_at: "2026-05-23T10:00:00+08:00",
            created_at: "2026-05-23T09:00:00+08:00",
            capability: "chat",
            message_count: 2,
            last_message: "先按承载力复习。",
            messages: [
              {
                id: "m1",
                role: "user",
                content: "怎么复习地基基础",
                created_at: "2026-05-23T09:00:00+08:00",
                capability: "chat",
              },
              {
                id: "m2",
                role: "assistant",
                content: "先按承载力复习。",
                created_at: "2026-05-23T09:01:00+08:00",
                capability: "chat",
              },
            ],
          },
        ],
      }),
    });
  });
}

test("BI v2 route does not render the global workspace sidebar", async ({ page }) => {
  await page.goto("/bi");

  await expect(page.getByText("BI 后台需 admin 登录")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "管理员用户名" })).toBeVisible();
  await expect(page.getByLabel("管理员密码")).toBeVisible();
  await expect(page.getByRole("button", { name: "登录后台" })).toBeVisible();
  await expect(page.getByText("新对话")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "聊天" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "收起侧边栏" })).toHaveCount(0);
});

test("BI v2 read-only details open for overview, feedback, and ops", async ({ page }) => {
  await installAdminSession(page);
  let feedbackTriageIdempotencyKey = "";
  let exportRequestIdempotencyKey = "";
  await mockBiV2ReadApis(page, {
    onFeedbackTriage: (key) => {
      feedbackTriageIdempotencyKey = key;
    },
    onExportRequest: (key) => {
      exportRequestIdempotencyKey = key;
    },
  });
  await page.goto("/bi");

  await expect(page.getByText("BI 后台需 admin 登录")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "经营总览" })).toBeVisible();
  await page.getByRole("button", { name: "打开 活跃学习会话 指标详情" }).click();
  await expect(page.getByRole("dialog", { name: "指标详情 · 活跃学习会话" })).toBeVisible();
  await expect(page.getByText("唯一 authority")).toBeVisible();
  await page.getByRole("button", { name: "关闭抽屉" }).click();

  await page.getByRole("button", { name: "查看 AI 反馈 negative 24h 增加" }).click();
  await expect(page.getByRole("dialog", { name: "行动项详情 · AI 反馈 negative 24h 增加" })).toBeVisible();
  await expect(page.getByText("建议处理区")).toBeVisible();
  await page.getByRole("button", { name: "关闭抽屉" }).click();

  await page.getByRole("textbox", { name: "全局搜索手机号 / user_id / 订单号" }).fill("ord_real_1");
  await page.getByRole("textbox", { name: "全局搜索手机号 / user_id / 订单号" }).press("Enter");
  await expect(page.getByRole("heading", { name: "商品账务" })).toBeVisible();
  await expect(page.getByText("全局搜索：")).toBeVisible();
  await expect(page.locator("code").filter({ hasText: "ord_real_1" }).first()).toBeVisible();
  await expect(page.getByText("入账流水 (1)")).toBeVisible();
  await page.getByRole("textbox", { name: "全局搜索手机号 / user_id / 订单号" }).fill("");
  await page.getByRole("textbox", { name: "全局搜索手机号 / user_id / 订单号" }).press("Enter");

  await page.getByRole("button", { name: "商品账务：套餐权益、入账流水、钱包流水、账务异常队列。" }).click();
  await expect(page.getByRole("heading", { name: "商品账务" })).toBeVisible();
  await expect(page.getByText("BI_COMMERCE_V2_ENABLED 已开启")).toBeVisible();
  await expect(page.getByText("入账流水 (1)")).toBeVisible();
  await page.getByRole("button", { name: "查看入账流水 ord_real_1 详情" }).click();
  await expect(page.getByText("authority：wallet_ledger · trust A")).toBeVisible();
  await page.getByRole("button", { name: "钱包流水 (2)" }).click();
  await page.getByRole("button", { name: "查看 ledger_real_1 元数据" }).click();
  await expect(page.getByText("reference：order /")).toBeVisible();
  await page.getByRole("button", { name: "套餐权益 (1)" }).click();
  await expect(page.getByText("精学版")).toBeVisible();

  await page.getByRole("button", { name: "反馈中心：AI 消息反馈与内测申请池，标记已看 / 忽略 / 归档。" }).click();
  await expect(page.getByText("storage=ok")).toBeVisible();
  await page.getByRole("button", { name: "查看反馈 fb_test_1 详情" }).click();
  const feedbackDialog = page.getByRole("dialog", { name: "反馈详情 · fb_test_1" });
  await expect(feedbackDialog).toBeVisible();
  await expect(feedbackDialog.getByText("学员反馈讲解不清楚")).toBeVisible();
  await expect(feedbackDialog.getByText("学情模块")).toBeVisible();
  await expect(feedbackDialog.getByText("数据不对")).toBeVisible();
  await expect(feedbackDialog.getByText("screen.png")).toBeVisible();
  await expect(feedbackDialog.getByText("页面：packageDeeptutor/pages/profile/profile")).toBeVisible();
  await page.getByRole("button", { name: "关闭抽屉" }).click();
  await page.getByRole("button", { name: "标记已看反馈 fb_test_1" }).click();
  await expect.poll(() => feedbackTriageIdempotencyKey).toMatch(/^[A-Za-z0-9_-]{1,128}$/);
  await expect(page.getByRole("button", { name: "标记已看反馈 fb_test_1" })).toBeDisabled();

  await page.getByRole("tab", { name: /内测申请/ }).click();
  await expect(page.getByRole("heading", { name: "内测申请池" })).toBeVisible();
  await expect(page.getByText("张同学")).toBeVisible();
  await page.getByRole("button", { name: "编辑内测申请 invite_1" }).click();
  const inviteDialog = page.getByRole("dialog", { name: "编辑内测申请 · 张同学" });
  await expect(inviteDialog).toBeVisible();
  await expect(inviteDialog.getByLabel("愿意回访且可联系")).toBeVisible();
  await page.getByRole("button", { name: "关闭抽屉" }).click();

  await page.getByRole("button", { name: "系统运维：成本质量、数据可信、操作审计、权限审计、上线面板。" }).click();
  await page.getByRole("button", { name: "查看 操作审计 详情" }).click();
  await expect(page.getByRole("dialog", { name: "运维详情 · 操作审计" })).toBeVisible();
  await page.getByRole("button", { name: "关闭抽屉" }).click();

  await page.getByRole("button", { name: "查看审计 audit_1 详情" }).click();
  await expect(page.getByRole("dialog", { name: "审计详情 · audit_1" })).toBeVisible();
  await expect(page.getByText("客服投诉")).toBeVisible();
  await page.getByRole("button", { name: "关闭抽屉" }).click();
  await page.getByRole("button", { name: "申请导出当前审计筛选" }).click();
  await expect.poll(() => exportRequestIdempotencyKey).toMatch(/^[A-Za-z0-9_-]{1,128}$/);
  await expect(page.getByText("操作审计导出")).toBeVisible();
  await expect(page.getByText("导出请求已写入 audit_export_1")).toBeVisible();
});

test("BI v2 member ops opens 360 and loads conversation details from the read endpoint", async ({
  page,
}) => {
  await installAdminSession(page);
  await mockBiV2ReadApis(page);
  let memberOpsActionIdempotencyKey = "";
  await mockMemberOpsApis(page, {
    onMemberOpsAction: (key) => {
      memberOpsActionIdempotencyKey = key;
    },
  });
  await page.goto("/bi?tab=member-ops");

  await expect(page.getByRole("heading", { name: "会员运营" })).toBeVisible();
  await page.getByRole("textbox", { name: "全局搜索手机号 / user_id / 订单号" }).fill("user_1");
  await page.getByRole("textbox", { name: "全局搜索手机号 / user_id / 订单号" }).press("Enter");
  await expect(page.getByRole("dialog", { name: "学员 360 · 139****0001" })).toBeVisible();
  await page.getByRole("button", { name: "关闭抽屉" }).click();
  let unexpectedPrompt = false;
  page.on("dialog", async (dialog) => {
    unexpectedPrompt = true;
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "把当前筛选与列设置保存为私有视图" }).click();
  await expect(page.getByRole("button", { name: "应用视图 视图 1" })).toBeVisible();
  expect(unexpectedPrompt).toBe(false);

  await page.getByRole("button", { name: "打开 user_1 学员 360" }).click();
  await expect(page.getByRole("dialog", { name: "学员 360 · 139****0001" })).toBeVisible();
  await page.getByRole("button", { name: "标记已联系", exact: true }).click();
  await expect.poll(() => memberOpsActionIdempotencyKey).toMatch(/^[A-Za-z0-9_-]{1,128}$/);
  await expect(page.getByText("已标记 139****0001 为已联系")).toBeVisible();

  await page.getByRole("button", { name: "查看会员对话回顾" }).click();
  await expect(page.getByRole("dialog", { name: "对话回顾 · 139****0001" })).toBeVisible();
  await expect(page.getByText("地基基础答疑")).toBeVisible();

  await page.getByLabel("客服投诉").check();
  await page
    .getByRole("button", { name: "查看 地基基础答疑 全文，将写入 audit" })
    .click();
  await expect(page.getByText("assistant: 先按承载力复习。")).toBeVisible();
  await expect(page.getByText("audit_test")).toBeVisible();
});

test("BI v2 legacy invite-test tab opens the feedback center invite application module", async ({
  page,
}) => {
  await installAdminSession(page);
  await mockBiV2ReadApis(page);
  await page.goto("/bi?tab=invite-test");

  await expect(page.getByRole("heading", { name: "反馈中心" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "内测申请池" })).toBeVisible();
  await expect(page.getByText("张同学")).toBeVisible();
});

test("BI v2 shell owns vertical scrolling inside the workspace frame", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 640 });
  await installAdminSession(page);
  await mockBiV2ReadApis(page);
  await mockMemberOpsApis(page, { memberCount: 40 });
  await page.goto("/bi?tab=member-ops");

  await expect(page.getByRole("heading", { name: "会员运营" })).toBeVisible();
  await expect(page.getByText("服务端返回前 40 / 40，当前筛选 40 行")).toBeVisible();

  const shell = page.locator("[data-bi-app-shell]");
  await expect(shell).toHaveCount(1);
  await expect
    .poll(async () =>
      shell.evaluate((el) => ({
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
      })),
    )
    .toMatchObject({ clientHeight: 640 });

  const canScroll = await shell.evaluate((el) => el.scrollHeight > el.clientHeight + 100);
  expect(canScroll).toBe(true);

  await shell.hover();
  await page.mouse.wheel(0, 900);
  await expect.poll(async () => shell.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);

  const bodyScroll = await page.evaluate(() => ({
    windowY: window.scrollY,
    documentTop: document.documentElement.scrollTop,
    bodyTop: document.body.scrollTop,
  }));
  expect(bodyScroll).toEqual({ windowY: 0, documentTop: 0, bodyTop: 0 });
});
