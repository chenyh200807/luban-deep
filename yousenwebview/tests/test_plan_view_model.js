// Run: node yousenwebview/tests/test_plan_view_model.js
// 计划页(跑道视图)视图模型域测试:
// 1. 顺序只来自服务端投影(零前端排序/自补任务);
// 2. 任务→动作复用 buildCanonicalLearningTask 唯一翻译器(路由字段逐一核对);
// 3. 收敛条只显示报告值(无报告→体检引导,禁造数);
// 4. 今日包完成态来自后端 completed 字段,前端不自算(缺字段=不显示完成态);
// 5. defer 手柄仅复习/learn 任务,复习必带 probe_id;
// 6. 未来天复验 display-only(未到期不可兑付,禁 dead click);
// 7. 回归防线: 源码禁 sort/自算优先级。
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var vmPath = path.join(__dirname, "../packageDeeptutor/utils/plan-view-model.js");
var vm = require(vmPath);

var LESSONS = {
  lessons: [
    { pack_id: "N01", title: "主体结构", light_practice_available: true },
    { pack_id: "N02", title: "施工测量", light_practice_available: false },
    { pack_id: "F16", title: "屋面防水", light_practice_available: true },
  ],
};

var REPORT = {
  pack_review: {
    enabled: true,
    degraded: false,
    authority: "revalidation_queue",
    due: [
      { pack_id: "F16", probe_id: "rvp_f16", retest_available: true },
    ],
  },
};

function reviewTask(overrides) {
  return Object.assign(
    {
      task: "review_probe",
      mode: "review_due",
      source_authority: "revalidation_queue",
      source_ref: "rvp_f16",
      target_pack_id: "F16",
      reason: "到期复验",
      why: "复习调度到期：错过会遗忘回退",
      evidence_refs: ["ev1"],
      expected_time: 5,
      completion_condition: "review_probe_completed:rvp_f16",
      retest_condition: "review_terminal_verified",
    },
    overrides || {},
  );
}

function practiceTask() {
  return {
    task: "practice_retest",
    mode: "practice_active",
    source_authority: "training_intent",
    source_ref: "ti_1",
    target_pack_id: "N01",
    reason: "继续练",
    why: "处方未完成：换皮复测闭环才算修复",
    evidence_refs: [],
    expected_time: 8,
    completion_condition: "retest_completed:N01",
    retest_condition: "forward_terminal_committed",
  };
}

function learnTask(overrides) {
  return Object.assign(
    {
      task: "learn_station",
      mode: "learn_next",
      source_authority: "pack_lifecycle_projection",
      source_ref: "N02",
      target_pack_id: "N02",
      reason: "下一站",
      why: "学序推进：registry 学序 + 前置边的下一未学站",
      evidence_refs: [],
      expected_time: 12,
      completion_condition: "station_completed:N02",
      retest_condition: "next_day_fresh_probe",
    },
    overrides || {},
  );
}

function planResp(overrides) {
  return Object.assign(
    {
      enabled: true,
      plan_policy_version: "exam_prep_plan_policy_v1",
      horizon_days: 7,
      days: [
        {
          date: "2026-08-05",
          day_offset: 0,
          planned_minutes: 25,
          tasks: [reviewTask(), practiceTask(), learnTask()],
        },
        {
          date: "2026-08-06",
          day_offset: 1,
          planned_minutes: 5,
          tasks: [
            reviewTask({ source_ref: "rvp_future", target_pack_id: "N01", why: "复习调度预报" }),
          ],
        },
      ],
      supply_gaps: [{ kind: "practice_retest", target_pack_id: "E01" }],
      next_step_arbitration: { mode: "review_due" },
      source_status: {
        authority: "exam_prep_plan_projection",
        daily_budget_minutes: 30,
        preference_applied: { pin: 0, defer: 0, time_budget: 0 },
        review_due_unavailable: false,
        unscheduled_count: 2,
      },
      pass_readiness: {
        estimated_score_band: "75-95",
        pass_line: 96,
        risk_band: "medium",
        generated_at: "2026-08-01T09:00:00Z",
      },
      exam_date: "2026-12-11",
      exam_countdown_days: 128,
    },
    overrides || {},
  );
}

// ── 1. flag off → enabled:false(页面占位,不渲染跑道) ──────────
assert.deepStrictEqual(vm.buildPlanViewModel({ planResp: { enabled: false } }), { enabled: false });
assert.deepStrictEqual(vm.buildPlanViewModel({}), { enabled: false });

// ── 2. 正常投影:顺序透传 + 头部收敛条 ─────────────────────────
var built = vm.buildPlanViewModel({ planResp: planResp(), lessons: LESSONS, report: REPORT });
assert.strictEqual(built.enabled, true);
assert.strictEqual(built.header.hasReadiness, true);
assert.strictEqual(built.header.scoreBand, "75-95");
assert.strictEqual(built.header.passLine, "96");
assert.strictEqual(built.header.riskLabel, "中风险");
assert.strictEqual(built.header.examCountdownDays, 128);
assert.strictEqual(built.days.length, 2);
assert.strictEqual(built.days[0].dayLabel, "今天");
assert.strictEqual(built.days[1].dayLabel, "明天");
assert.strictEqual(built.days[0].plannedMinutes, 25);
// 顺序=服务端投影顺序(零前端重排)
assert.deepStrictEqual(
  built.days[0].tasks.map(function (t) { return t.family; }),
  ["review_probe", "practice_retest", "learn_station"],
);

// ── 3. 今日任务经唯一翻译器路由(与 learn.js goTodayTask 同语义) ──
var reviewView = built.days[0].tasks[0];
assert.strictEqual(reviewView.ctaLabel, "开始验证", "到期复验 CTA 来自翻译器");
assert.ok(reviewView.actionUrl.indexOf("/pages/luban/retest/retest?pack_id=F16") >= 0);
assert.ok(reviewView.actionUrl.indexOf("mode=review") >= 0);
assert.ok(reviewView.actionUrl.indexOf("probe_id=rvp_f16") >= 0);
assert.strictEqual(reviewView.title, "屋面防水", "标题来自 lessons manifest");

var practiceView = built.days[0].tasks[1];
assert.strictEqual(practiceView.ctaLabel, "集中练习");
assert.ok(practiceView.actionUrl.indexOf("pack_id=N01") >= 0);
assert.ok(practiceView.actionUrl.indexOf("mode=forward") >= 0);
assert.ok(practiceView.actionUrl.indexOf("training_intent_id=ti_1") >= 0);

var learnView = built.days[0].tasks[2];
// N02 练习池未签发 → 翻译器裁决为进站看讲解(lesson 路由),禁自判供给
assert.ok(learnView.actionUrl.indexOf("/pages/luban/station/station") >= 0);
assert.ok(learnView.actionUrl.indexOf("pack_id=N02") >= 0);

// ── 4. defer 手柄:仅复习/learn;复习必带 probe_id ─────────────
assert.strictEqual(reviewView.canDefer, true);
assert.strictEqual(reviewView.deferProbeId, "rvp_f16", "复习 defer 必带 probe_id");
assert.strictEqual(practiceView.canDefer, false, "practice 无 defer 手柄");
assert.strictEqual(learnView.canDefer, true);
assert.strictEqual(learnView.deferProbeId, "", "learn defer 不带 probe_id");

// ── 5. 未来天复验 display-only(未到期不可兑付,禁 dead click) ──
var futureReview = built.days[1].tasks[0];
assert.strictEqual(futureReview.actionUrl, "", "未来复验不给路由");
assert.strictEqual(futureReview.ctaLabel, "");
assert.strictEqual(futureReview.canDefer, false, "defer 只对今天");
assert.ok(futureReview.supplyNote.length > 0, "给确定性说明");

// ── 6. 今日包完成态:来自后端字段,缺字段=不显示完成态 ──────────
assert.strictEqual(built.todayComplete, false, "无 completed 字段 → 不自算完成");
var completedResp = planResp();
completedResp.days[0].tasks = completedResp.days[0].tasks.map(function (t) {
  return Object.assign({}, t, { completed: true });
});
var builtDone = vm.buildPlanViewModel({ planResp: completedResp, lessons: LESSONS, report: REPORT });
assert.strictEqual(builtDone.todayComplete, true, "后端全 completed → 打卡态");

// ── 7. 日级证据文案位:数据没有就不显示(禁造数) ────────────────
assert.strictEqual(built.todayEvidenceNote, "", "无数据 → 整块不显示");
var withEvidence = planResp();
withEvidence.source_status.today_positive_evidence_count = 3;
var builtEv = vm.buildPlanViewModel({ planResp: withEvidence, lessons: LESSONS, report: REPORT });
assert.strictEqual(builtEv.todayEvidenceNote, "今日新增 3 条正面证据");

// ── 8. 无报告 → 体检引导(不造带子) ────────────────────────────
var noReadiness = planResp({ pass_readiness: null, exam_countdown_days: null });
var builtGuide = vm.buildPlanViewModel({ planResp: noReadiness, lessons: LESSONS, report: REPORT });
assert.strictEqual(builtGuide.header.hasReadiness, false);
assert.strictEqual(builtGuide.header.scoreBand, "");
assert.strictEqual(builtGuide.header.examCountdownDays, null);

// ── 9. deferred 任务态 + learn_fallback display-only ──────────
var deferredResp = planResp();
deferredResp.days[1].tasks[0].status = "deferred";
var builtDeferred = vm.buildPlanViewModel({ planResp: deferredResp, lessons: LESSONS, report: REPORT });
assert.strictEqual(builtDeferred.days[1].tasks[0].deferred, true);
var fallbackResp = planResp();
fallbackResp.days[0].tasks = [
  learnTask({ mode: "learn_fallback", source_authority: "pack_manifest.registry_order" }),
];
var builtFallback = vm.buildPlanViewModel({ planResp: fallbackResp, lessons: LESSONS, report: REPORT });
assert.strictEqual(builtFallback.days[0].tasks[0].actionUrl, "", "翻译器无映射 → display-only,禁自写路由");

// ── 10. 供给缺口/未排任务计数透传 ─────────────────────────────
assert.strictEqual(built.supplyGapCount, 1);
assert.strictEqual(built.unscheduledCount, 2);

// ── 11. 回归防线:视图模型源码禁前端排序/自算优先级 ─────────────
var source = fs.readFileSync(vmPath, "utf8");
assert.ok(source.indexOf(".sort(") < 0, "计划页零前端排序(顺序=服务端投影)");
assert.ok(source.indexOf("gap_score") < 0 && source.indexOf("gapScore") < 0, "禁自算优先级");

console.log("test_plan_view_model: all assertions passed");
