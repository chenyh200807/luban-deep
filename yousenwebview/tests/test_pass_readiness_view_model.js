// Run: node yousenwebview/tests/test_pass_readiness_view_model.js
// 过线体检(S5)旅程侧视图模型域测试:
// 1. 落地页六要素文案(§4.1 逐字) + 登录车道解析(§5.1: 拒绝=basic 车道同 handler);
// 2. 会话规整: checkpoint_after 唯一来源=服务端(缺失→0, 禁前端写死 6)、
//    三题型纯点选、案例微进度「案例 i/n」;
// 3. 中场检查点(§6.2): 触发条件、粗带只投影服务端字段、零证据/零弱点字段;
// 4. 本地草稿 + 服务端 resume 合并(冲突服务端赢);
// 5. 提交 wire = dict[str,str];
// 6. 完成后落点路由参数化常量。
var assert = require("assert");
var path = require("path");

var vmPath = path.join(
  __dirname,
  "../packageDeeptutor/utils/pass-readiness-view-model.js",
);
var vm = require(vmPath);

// ── 1. 落地页六要素 ──────────────────────────────────────────
assert.strictEqual(vm.LANDING_COPY.productName, "鲁班智考 · 一建过线体检");
assert.strictEqual(vm.LANDING_COPY.h1, "离 96 分过线，你还差几分？");
assert.ok(
  vm.LANDING_COPY.subtitle.indexOf("2015–2025") >= 0 &&
    vm.LANDING_COPY.subtitle.indexOf("采分点") >= 0,
  "副标必须含十一年真题与采分点定位",
);
assert.ok(
  vm.LANDING_COPY.antiQuizLine.indexOf("不是心理测试") === 0,
  "防心测声明必须打头",
);
assert.strictEqual(vm.LANDING_COPY.ctaLogin, "微信一键登录 · 开始测评");
assert.ok(
  vm.LANDING_COPY.phoneAuthReason.indexOf("不影响本次测评") >= 0 &&
    vm.LANDING_COPY.phoneAuthReason.indexOf("可随时退订") >= 0,
  "授权理由文案必须按 §5.1 逐字要点",
);
assert.strictEqual(
  vm.LANDING_COPY.phoneAuthReason.indexOf("不外呼"),
  -1,
  "禁承诺不外呼(§5.1)",
);

// ── 2. 登录车道解析 ──────────────────────────────────────────
var granted = vm.resolveLoginLane({ code: "phone-code-1", errMsg: "getPhoneNumber:ok" });
assert.strictEqual(granted.lane, "phone");
assert.strictEqual(granted.phoneCode, "phone-code-1");

var declined = vm.resolveLoginLane({ errMsg: "getPhoneNumber:fail user deny" });
assert.strictEqual(declined.lane, "basic", "拒绝必须走 login-basic 车道");
assert.strictEqual(declined.privacyInterrupted, false);

var privacy = vm.resolveLoginLane({ errMsg: "getPhoneNumber:fail privacy permission is not authorized" });
assert.strictEqual(privacy.lane, "basic");
assert.strictEqual(privacy.privacyInterrupted, true, "隐私中断必须单独识别, 不算手机号拒绝");

var legacyShape = vm.resolveLoginLane({ phoneCode: "phone-code-2" });
assert.strictEqual(legacyShape.lane, "phone");

// ── 3. 会话规整 ──────────────────────────────────────────────
var sessionPayload = {
  quiz_id: "quiz_pr_1",
  checkpoint_after: 6,
  scored_count: 12,
  profile_count: 3,
  blueprint_version: "pass_readiness_architecture_v1",
  questions: [
    {
      question_id: "s1",
      question_stem: "单选计分题",
      question_type: "single_choice",
      options: [{ key: "A", text: "甲" }, { key: "B", text: "乙" }],
    },
    {
      question_id: "m1",
      question_stem: "多选计分题",
      question_type: "multi_choice",
      options: [{ key: "A", text: "甲" }, { key: "B", text: "乙" }],
    },
    {
      question_id: "c1",
      question_stem: "案例一第 1 问",
      question_type: "single_choice",
      case_id: "case_a",
      options: [{ key: "A", text: "甲" }],
    },
    {
      question_id: "c2",
      question_stem: "案例二第 1 问",
      question_type: "single_choice",
      case_id: "case_b",
      options: [{ key: "A", text: "甲" }],
    },
    {
      question_id: "p1",
      question_stem: "你考过几次一建？",
      question_type: "profile_probe",
      options: [{ key: "A", text: "第一次" }],
    },
    {
      question_id: "x1",
      question_stem: "未知类型题",
      question_type: "essay",
      options: [{ key: "A", text: "甲" }],
    },
  ],
  draft_answer_snapshot: { s1: "A" },
};
var session = vm.normalizeSession(sessionPayload);
assert.strictEqual(session.quizId, "quiz_pr_1");
assert.strictEqual(session.checkpointAfter, 6);
assert.strictEqual(session.scoredCount, 12);
assert.strictEqual(session.profileCount, 3);
assert.strictEqual(session.questions.length, 6);
assert.strictEqual(session.questions[4].question_type, "profile_probe");
assert.strictEqual(session.questions[4].scored, false, "profile_probe 不计分");
assert.strictEqual(
  session.questions[5].question_type,
  "single_choice",
  "未知类型收敛为纯点选单选, 不引入新交互",
);
assert.strictEqual(session.questions[2].caseTag, "案例 1/2");
assert.strictEqual(session.questions[3].caseTag, "案例 2/2");
assert.strictEqual(session.questions[0].caseTag, "", "非案例题不带案例微进度");
assert.deepStrictEqual(session.serverAnswers, { s1: "A" });

// checkpoint_after 缺失 → 0(禁前端默认 6)
var noCheckpoint = vm.normalizeSession({
  quiz_id: "q2",
  questions: sessionPayload.questions,
});
assert.strictEqual(noCheckpoint.checkpointAfter, 0, "checkpoint_after 缺失必须为 0, 前端不得写死 6");

// ── 4. 中场检查点 ────────────────────────────────────────────
assert.strictEqual(vm.shouldShowCheckpoint(session, 5, false), false);
assert.strictEqual(vm.shouldShowCheckpoint(session, 6, false), true);
assert.strictEqual(vm.shouldShowCheckpoint(session, 6, true), false, "看过一次不再打断");
assert.strictEqual(
  vm.shouldShowCheckpoint(noCheckpoint, 12, false),
  false,
  "服务端未下发 checkpoint_after 时永不触发",
);

var checkpoint = vm.buildCheckpointModel(session);
assert.ok(checkpoint.title.indexOf("6/12") >= 0);
assert.strictEqual(checkpoint.coverageLabel, "证据覆盖：低");
assert.strictEqual(
  checkpoint.cta,
  "再答 6 题：收窄分数带 + 定位失分采分点",
  "唯一 CTA 文案按任务契约, 余量由数据算出",
);
assert.strictEqual(checkpoint.bandLine, "", "服务端未给粗带字段时不本地造数");
var checkpointWithBand = vm.buildCheckpointModel(
  Object.assign({}, session, { midpointBand: "60–120 分" }),
);
assert.strictEqual(checkpointWithBand.bandLine, "60–120 分", "粗带只投影服务端字段");
// 检查点模型零证据/零弱点字段(§6.2 红线)
Object.keys(checkpoint).forEach(function (key) {
  assert.ok(
    ["title", "coverageLabel", "coverageLine", "bandLine", "cta"].indexOf(key) >= 0,
    "检查点模型出现越界字段: " + key,
  );
});
var checkpointText = JSON.stringify(checkpoint);
["弱点", "错误", "答错", "采分点证据"].forEach(function (word) {
  assert.strictEqual(
    checkpointText.indexOf(word),
    -1,
    "检查点屏禁出证据/弱点表述: " + word,
  );
});

// ── 5. 草稿合并(服务端赢)与进度 ─────────────────────────────
var merged = vm.mergeResumeAnswers({ s1: "B", c1: "A" }, { s1: "A", m1: "AB" });
assert.strictEqual(merged.s1, "B", "同题冲突服务端赢");
assert.strictEqual(merged.m1, "AB", "服务端没有的题保留本地草稿");
assert.strictEqual(merged.c1, "A");

var answerState = vm.buildAnswerState(session.questions, merged, 1);
assert.strictEqual(answerState.answeredCount, 3);
assert.strictEqual(answerState.answeredScoredCount, 3);
assert.strictEqual(answerState.answerSheet[1].current, true);

var draft = vm.buildDraft("quiz_pr_1", merged, 2, true);
assert.strictEqual(draft.quizId, "quiz_pr_1");
assert.strictEqual(draft.checkpointSeen, true);
assert.strictEqual(draft.currentIndex, 2);

// ── 6. 提交 wire ─────────────────────────────────────────────
var answers = vm.buildSubmitAnswers({ s1: "A", m1: "AB", empty: "" });
assert.deepStrictEqual(answers, { s1: "A", m1: "AB" }, "提交 wire 必须是 dict[str,str] 且过滤空值");

// ── 7. 完成后落点路由(参数化常量) ────────────────────────────
var landing = vm.postDiagnosticLandingRoute("quiz_pr_1");
assert.ok(
  landing.indexOf("/packageDeeptutor/pages/luban/pass-readiness/report/report") === 0,
  "当前落点=报告页保存成功态(计划页二波交付后只改常量)",
);
assert.ok(landing.indexOf("section=saved") >= 0);
assert.ok(landing.indexOf("quiz_id=quiz_pr_1") >= 0);

console.log("PASS test_pass_readiness_view_model.js");
