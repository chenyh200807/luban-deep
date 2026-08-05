// Run: node yousenwebview/tests/test_pass_readiness_report_page_contract.js
// 过线体检报告页(屏 3-9)合同:
// 1. 报告加载: 提交快照优先; 无 quiz_id 时用 diagnostic_sources 兜底(唯一判断源),
//    未完成 → 诚实错误态;
// 2. 屏序: result → evidence → plan → save(每屏一个主 CTA);
// 3. 保存屏: 手机号已知=直接保存 → 参数化落点(当前=saved 态);
//    openid-only 二次授权, 拒绝零弹窗零 toast 且不拦结果, 授权走 bindPhone;
// 4. 微课/复测跳既有路由; 复测返回 → 收据屏; 会员 CTA → 既有 billing;
// 5. WXML: lesson 按钮以绑定存在为条件渲染(禁 dead button);
//    计划预览 pending 态只有骨架无按钮; 检查§7.2 关键绑定在场。
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pageDir = path.join(
  __dirname,
  "../packageDeeptutor/pages/luban/pass-readiness/report",
);
var source = fs.readFileSync(path.join(pageDir, "report.js"), "utf8");
var wxml = fs.readFileSync(path.join(pageDir, "report.wxml"), "utf8");

// ── 5. WXML 结构合同 ────────────────────────────────────────
assert.ok(
  wxml.indexOf('wx:if="{{item.lessonPackId}}"') >= 0,
  "微课按钮必须以绑定存在为渲染条件(禁 dead button)",
);
assert.ok(wxml.indexOf("evidence.lessonMissingCopy") >= 0, "无绑定必须给诚实占位文案");
[
  "result.bandText",
  "result.passLine",
  "result.readinessTier",
  "result.riskLine",
  "result.evidenceCoverageLabel",
  "result.disclaimer",
  "result.bandUnavailableCopy",
  "result.selfReportedScoreLabel",
  "item.pitfall",
  "item.whyMissed",
  "receipt.headline",
  "save.declineNote",
  "member.copy",
].forEach(function (binding) {
  assert.ok(wxml.indexOf(binding) >= 0, "报告页缺关键绑定: " + binding);
});
assert.ok(
  wxml.indexOf('wx:if="{{result.showReferenceInterval}}"') >= 0,
  "reference_pass_interval 空串必须不渲染",
);
// 计划 pending 分支内不得有可点按钮
var pendingBlock = wxml.slice(
  wxml.indexOf("plan.status === 'pending'"),
  wxml.indexOf("</block>", wxml.indexOf("plan.status === 'pending'")),
);
assert.strictEqual(pendingBlock.indexOf("bindtap"), -1, "计划 loading 态禁假按钮");

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

var SAMPLE_REPORT = {
  schema_version: "p0a-v1",
  pass_readiness: {
    band_status: "ok",
    estimated_score_band: "75–95 分",
    band_lower: 75,
    band_upper: 95,
    pass_line: 96,
    ability_readiness: "中低 (55–65)",
    prep_feasibility: "时间预算偏紧",
    risk_band: "临界不稳",
    evidence_coverage: "medium",
    reference_pass_interval: "45%–60%",
    unmeasured_dimensions: ["answer_expression"],
    self_reported_score_label: "自报未核验",
  },
  evidence_items: [
    {
      question_stem: "模板拆除顺序",
      learner_answer: "B",
      scoring_point: "后支的先拆",
      pitfall: "",
      why_missed: "判断停在正向顺序。",
      source: "教材 2026 · 第 3 章",
      lesson_pack_id: "F16",
      retest_pack_id: "F16",
    },
  ],
};

function loadPage(overrides) {
  var calls = {
    navigateTo: [],
    redirectTo: [],
    toasts: [],
    modals: [],
    bindPhoneCalls: [],
    reportFetches: [],
    ownerStorage: {},
  };
  if (overrides && overrides.snapshot) {
    calls.ownerStorage["deeptutor.passReadiness.lastReport"] = overrides.snapshot;
  }
  var apiMock = Object.assign(
    {
      getAssessmentReport: function (quizId) {
        calls.reportFetches.push(quizId);
        return Promise.resolve(SAMPLE_REPORT);
      },
      getAssessmentProfile: function () {
        return Promise.resolve(
          (overrides && overrides.profile) || {
            diagnostic_sources: {
              pass_readiness: { completed: true, quiz_id: "quiz_hist", scored_at: "2026-08-05" },
            },
          },
        );
      },
      getUserInfo: function () {
        return Promise.resolve({
          phone: overrides && overrides.hasPhone ? "13800000000" : "",
        });
      },
      bindPhone: function (phoneCode) {
        calls.bindPhoneCalls.push(phoneCode);
        return Promise.resolve({ ok: true });
      },
      unwrapResponse: function (raw) {
        return (raw && raw.data) || raw;
      },
      describeRequestError: function (err, fallback) {
        return fallback;
      },
    },
    (overrides && overrides.api) || {},
  );
  var pageDef = null;
  var sandbox = {
    console: console,
    Promise: Promise,
    Date: Date,
    setTimeout: setTimeout,
    String: String,
    Object: Object,
    require: function (request) {
      if (request === "../../../../utils/api") return apiMock;
      if (request === "../../../../utils/auth") {
        return {
          readOwnerStorage: function (key) {
            return calls.ownerStorage[key];
          },
          writeOwnerStorage: function (key, value) {
            calls.ownerStorage[key] = value;
            return true;
          },
        };
      }
      if (request === "../../../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDarkOr: function () {
            return false;
          },
        };
      }
      if (request === "../../../../utils/route") {
        return {
          lubanStation: function (packId) {
            return "/packageDeeptutor/pages/luban/station/station?pack_id=" + packId;
          },
          billing: function () {
            return "/packageDeeptutor/pages/billing/billing";
          },
          lubanPassReadiness: function () {
            return "/packageDeeptutor/pages/luban/pass-readiness/landing/landing";
          },
          lubanPassReadinessExam: function () {
            return "/packageDeeptutor/pages/luban/pass-readiness/exam/exam";
          },
        };
      }
      if (request === "../../../../utils/surface-telemetry") {
        return {
          trackProductBehavior: function () {},
          trackModuleView: function () {},
          trackModuleExit: function () {},
        };
      }
      if (request === "../../../../utils/pass-readiness-view-model") {
        return require(path.join(__dirname, "../packageDeeptutor/utils/pass-readiness-view-model"));
      }
      if (request === "../../../../utils/pass-readiness-report-view-model") {
        return require(path.join(__dirname, "../packageDeeptutor/utils/pass-readiness-report-view-model"));
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      navigateTo: function (opts) {
        calls.navigateTo.push(opts.url);
      },
      redirectTo: function (opts) {
        calls.redirectTo.push(opts.url);
        if (overrides && overrides.redirectFails && opts.fail) opts.fail();
      },
      showToast: function (opts) {
        calls.toasts.push(opts);
      },
      showModal: function (opts) {
        calls.modals.push(opts);
      },
      navigateBack: function () {},
      reLaunch: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };
  vm.runInNewContext(source, sandbox, { filename: "report.js" });
  var page = {
    data: Object.assign({}, pageDef.data),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, calls: calls };
}

(async function main() {
  // ── 1. 快照优先 + §7.2 投影落地 ──
  var loaded = loadPage({
    snapshot: { quizId: "quiz_pr_1", report: SAMPLE_REPORT, savedAt: 1 },
    hasPhone: true,
  });
  loaded.page.onLoad({ quiz_id: "quiz_pr_1" });
  await flushPromises();
  assert.strictEqual(loaded.page.data.stage, "ready");
  assert.strictEqual(loaded.calls.reportFetches.length, 0, "快照命中不再拉服务端");
  assert.strictEqual(loaded.page.data.result.bandText, "75–95 分");
  assert.strictEqual(loaded.page.data.result.gapLine, "离过线还差最多 21 分");
  assert.strictEqual(loaded.page.data.result.expressionMeasured, false);
  assert.strictEqual(loaded.page.data.evidence.items[0].pitfall, "该采分点的易错点整理中");
  assert.strictEqual(loaded.page.data.plan.status, "pending");

  // ── 2. 屏序 ──
  assert.strictEqual(loaded.page.data.section, "result");
  loaded.page.onPrimaryCta();
  assert.strictEqual(loaded.page.data.section, "evidence");
  loaded.page.onEvidenceContinue();
  assert.strictEqual(loaded.page.data.section, "plan");
  loaded.page.onPlanContinue();
  assert.strictEqual(loaded.page.data.section, "save");

  // ── 3a. 手机号已知: 直接保存 → 参数化落点 = 计划页(跑道反转第 1 步) ──
  await flushPromises();
  assert.strictEqual(loaded.page.data.save.mode, "direct");
  loaded.page.onSaveDirect();
  var landingUrl = loaded.calls.redirectTo[loaded.calls.redirectTo.length - 1];
  assert.ok(
    landingUrl.indexOf("/packageDeeptutor/pages/luban/plan/plan") === 0,
    "保存后落点=计划页(G 线冻结路由)",
  );
  assert.ok(landingUrl.indexOf("entry_source=pass_readiness") >= 0);
  assert.ok(landingUrl.indexOf("quiz_id=quiz_pr_1") >= 0);

  // 汇合前回退: 计划页未注册 → redirect fail → 本页保存成功态, 流程不断
  var fallback = loadPage({
    snapshot: { quizId: "quiz_pr_1", report: SAMPLE_REPORT, savedAt: 1 },
    hasPhone: true,
    redirectFails: true,
  });
  fallback.page.onLoad({ quiz_id: "quiz_pr_1", section: "save" });
  await flushPromises();
  fallback.page.onSaveDirect();
  assert.strictEqual(fallback.page.data.section, "saved", "redirect 失败回退保存成功态");
  fallback.page.onSavedContinue();
  assert.strictEqual(fallback.page.data.section, "member");
  fallback.page.onMembershipCta();
  assert.ok(
    fallback.calls.navigateTo[fallback.calls.navigateTo.length - 1].indexOf("billing") >= 0,
    "会员 handoff 走既有 billing 面",
  );

  // ── 3b. openid-only: 拒绝零弹窗零 toast 不拦结果; 授权走 bindPhone ──
  var openidOnly = loadPage({
    snapshot: { quizId: "quiz_pr_1", report: SAMPLE_REPORT, savedAt: 1 },
    hasPhone: false,
    redirectFails: true, // 汇合前环境: 绑定成功后回退保存成功态
  });
  openidOnly.page.onLoad({ quiz_id: "quiz_pr_1", section: "save" });
  await flushPromises();
  assert.strictEqual(openidOnly.page.data.save.mode, "phone_auth");
  openidOnly.page.handleSavePhoneNumber({ detail: { errMsg: "getPhoneNumber:fail user deny" } });
  await flushPromises();
  assert.strictEqual(openidOnly.calls.bindPhoneCalls.length, 0);
  assert.strictEqual(openidOnly.calls.toasts.length, 0, "保存屏拒绝零 toast");
  assert.strictEqual(openidOnly.calls.modals.length, 0, "保存屏拒绝零弹窗");
  assert.strictEqual(openidOnly.page.data.section, "save", "拒绝后仍可看结果, 不跳转不拦截");
  openidOnly.page.handleSavePhoneNumber({ detail: { code: "phone-code-save" } });
  await flushPromises();
  assert.deepStrictEqual(openidOnly.calls.bindPhoneCalls, ["phone-code-save"]);
  assert.strictEqual(openidOnly.page.data.section, "saved");

  // ── 4. 微课/复测跳既有路由; 复测返回 → 收据屏 ──
  var journey = loadPage({
    snapshot: { quizId: "quiz_pr_1", report: SAMPLE_REPORT, savedAt: 1 },
    hasPhone: true,
  });
  journey.page.onLoad({ quiz_id: "quiz_pr_1", section: "evidence" });
  await flushPromises();
  journey.page.onOpenLesson({ currentTarget: { dataset: { packId: "F16" } } });
  assert.ok(journey.calls.navigateTo[0].indexOf("station/station?pack_id=F16") >= 0);
  journey.page.onOpenLesson({ currentTarget: { dataset: { packId: "" } } });
  assert.strictEqual(journey.calls.navigateTo.length, 1, "无绑定不导航");
  journey.page.onOpenRetest({ currentTarget: { dataset: { packId: "F16" } } });
  assert.ok(journey.calls.navigateTo[1].indexOf("retest/retest?pack_id=F16") >= 0);
  journey.page.onShow();
  assert.strictEqual(journey.page.data.section, "receipt", "复测返回展示证明收据屏");
  assert.strictEqual(
    journey.page.data.receipt.headline,
    "同一采分点、同难度锚的平行题，这次拿到了——这是一次新的正面证据",
  );
  journey.page.onReceiptContinue();
  assert.strictEqual(journey.page.data.section, "save");

  // ── 1b. 无 quiz_id 且未完成过 → 诚实错误态 ──
  var fresh = loadPage({ profile: { diagnostic_sources: {} } });
  fresh.page.onLoad({});
  await flushPromises();
  assert.strictEqual(fresh.page.data.stage, "error");
  assert.ok(fresh.page.data.errorText.indexOf("先做一次诊断") >= 0);

  // ── 1c. 无 quiz_id 但 diagnostic_sources 指向历史 → 拉那份报告 ──
  var hist = loadPage({});
  hist.page.onLoad({});
  await flushPromises();
  assert.deepStrictEqual(hist.calls.reportFetches, ["quiz_hist"], "历史入口只信 diagnostic_sources");
  assert.strictEqual(hist.page.data.stage, "ready");

  console.log("PASS test_pass_readiness_report_page_contract.js");
})().catch(function (err) {
  console.error(err);
  process.exit(1);
});
