// Run: node yousenwebview/tests/test_pass_readiness_report_view_model.js
// 过线体检结果侧视图模型域测试:
// 1. §7.2 字段契约投影(band/pass_line/readiness/feasibility/risk/coverage/interval);
// 2. band_status=evidence_insufficient → 诚实空态, 不造分数带;
// 3. reference_pass_interval 空串 → 不渲染;
// 4. 首屏精确整数纪律: 结果模型不输出精确整数就绪度字段;
// 5. 证据屏槽位 + 易错点空槽诚实占位 + 绑定缺失禁 dead button;
// 6. 计划预览 loading 态零假数据; 收据文案逐字; 保存/会员文案红线(§4.2/§4.3/§8.3)。
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var vmPath = path.join(
  __dirname,
  "../packageDeeptutor/utils/pass-readiness-report-view-model.js",
);
var vm = require(vmPath);

// ── 1. §7.2 契约投影 ─────────────────────────────────────────
var report = {
  estimated_score_band: "75–95 分",
  pass_line: 96,
  ability_readiness: "中低 (55–65)",
  prep_feasibility: "时间预算偏紧",
  risk_band: "临界不稳",
  evidence_coverage: "medium",
  band_policy_version: "band-v1",
  reference_pass_interval: "45%–60%",
  diagnosis: "主要失分集中在案例采分点检索，而且马上能补。",
};
var result = vm.buildResultModel(report);
assert.strictEqual(result.bandAvailable, true);
assert.strictEqual(result.bandText, "75–95 分");
assert.strictEqual(result.passLine, 96);
assert.strictEqual(result.passLineLabel, "过线 96 分");
assert.strictEqual(result.riskBand, "临界不稳");
assert.strictEqual(result.readinessTier, "中低");
assert.strictEqual(result.readinessRange, "55–65");
assert.strictEqual(result.prepFeasibility, "时间预算偏紧");
assert.strictEqual(result.evidenceCoverageLabel, "中");
assert.strictEqual(result.bandPolicyVersion, "band-v1");
assert.strictEqual(result.showReferenceInterval, true);
assert.strictEqual(result.referencePassInterval, "45%–60%");
assert.strictEqual(result.primaryCta, "先补最影响得分的这一点");
assert.strictEqual(result.gapLine, "离过线还差最多 21 分", "损失框架 = pass_line − band_low");
assert.ok(result.geometry && result.geometry.passLinePct > result.geometry.bandLeftPct);
assert.ok(
  result.disclaimer.indexOf("尚未经过真实考试结果校准") >= 0,
  "信任声明必须逐字保留未校准边界",
);

// ── 2. 证据不足 → 诚实空态 ───────────────────────────────────
var insufficient = vm.buildResultModel({
  estimated_score_band: null,
  band_status: "evidence_insufficient",
  pass_line: 96,
  evidence_coverage: "low",
  reference_pass_interval: "",
});
assert.strictEqual(insufficient.bandAvailable, false);
assert.strictEqual(insufficient.bandText, "");
assert.strictEqual(insufficient.geometry, null, "无带不画带");
assert.strictEqual(insufficient.gapLine, "");
assert.ok(insufficient.bandUnavailableCopy.length > 0, "空态必须有诚实解释文案");
// ── 3. low 档 interval 空串不渲染 ────────────────────────────
assert.strictEqual(insufficient.showReferenceInterval, false);

// ── 4. 首屏精确整数纪律 ──────────────────────────────────────
Object.keys(result).forEach(function (key) {
  if (key === "passLine") return; // 过线线 96 是契约常量, 允许
  var value = result[key];
  assert.ok(
    !(typeof value === "number" && key.toLowerCase().indexOf("readiness") >= 0),
    "首屏模型禁出精确整数就绪度字段: " + key,
  );
});
assert.strictEqual(typeof result.readinessTier, "string");
assert.strictEqual(typeof result.readinessRange, "string");

// ── 5. 证据屏 ────────────────────────────────────────────────
var evidence = vm.buildEvidenceModel({
  evidence_items: [
    {
      question_stem: "案例题:模板拆除顺序",
      learner_answer: "B",
      scoring_point: "先支后拆、后支先拆",
      scoring_wording: "写出「后支的先拆」即可得 2 分",
      pitfall: "常见错误是按施工顺序正向拆除",
      why_missed: "你的判断停在正向顺序，这题考的是逆序拆除条件。",
      source: "教材 2026 版 · 第 3 章模板工程",
      lesson_pack_id: "F16",
      retest_pack_id: "F16",
    },
    {
      question_stem: "第二题",
      learner_answer: "A",
      scoring_point: "另一采分点",
      pitfall: "",
      why_missed: "",
      source: "教材 2026 版",
    },
  ],
});
assert.strictEqual(evidence.items.length, 2);
assert.strictEqual(evidence.isEmpty, false);
assert.strictEqual(evidence.items[0].pitfallAvailable, true);
assert.strictEqual(evidence.items[1].pitfallAvailable, false);
assert.strictEqual(
  evidence.items[1].pitfall,
  "该采分点的易错点整理中",
  "易错点空槽必须诚实占位而非伪造",
);
assert.strictEqual(evidence.items[0].lessonPackId, "F16");
assert.strictEqual(evidence.items[1].lessonPackId, "", "无绑定则空 → 页面不渲染按钮(禁 dead button)");
assert.ok(evidence.lessonMissingCopy.length > 0);

// ── 6. 计划预览 loading 态 ───────────────────────────────────
var pendingPlan = vm.buildPlanPreviewModel(null);
assert.strictEqual(pendingPlan.status, "pending");
assert.strictEqual(pendingPlan.items.length, 0, "loading 态零假数据");
assert.strictEqual(pendingPlan.slots.length, 3, "三优先静态结构槽");
pendingPlan.slots.forEach(function (slot) {
  assert.ok(!slot.cta && !slot.url, "loading 态禁假按钮");
});
var readyPlan = vm.buildPlanPreviewModel({
  items: [
    { title: "补模板拆除采分点", desc: "微课+复测", evidence_source: "本次诊断", expected_time: "10 分钟" },
    { title: "风险 2", desc: "" },
    { title: "风险 3", desc: "" },
    { title: "溢出项", desc: "" },
  ],
});
assert.strictEqual(readyPlan.status, "ready");
assert.strictEqual(readyPlan.items.length, 3, "只取前三优先");

// ── 7. 收据 / 保存 / 会员 ────────────────────────────────────
var receipt = vm.buildReceiptModel();
assert.strictEqual(
  receipt.headline,
  "同一采分点、同难度锚的平行题，这次拿到了——这是一次新的正面证据",
);
assert.ok(receipt.subline.indexOf("还不等于稳定掌握") >= 0, "收据禁说已掌握");

var savedDirect = vm.buildSaveModel(true);
assert.strictEqual(savedDirect.mode, "direct");
var savePhone = vm.buildSaveModel(false);
assert.strictEqual(savePhone.mode, "phone_auth");
assert.ok(savePhone.declineNote.indexOf("继续查看") >= 0, "拒绝仍可看结果");

var member = vm.buildMembershipCta({ daysToExam: 92 });
assert.ok(member.copy.indexOf("刚才这个点你已经补上") === 0);
assert.ok(member.copy.indexOf("距考试还有 92 天") >= 0);
assert.ok(member.copy.indexOf("再等一年") >= 0, "损失框架必须在场(§8.3)");
var memberNoDays = vm.buildMembershipCta({});
assert.strictEqual(memberNoDays.copy.indexOf("距考试"), -1, "无考期数据不编天数");
var personalized = vm.buildMembershipCta({
  passedSubjectLine: "你 2025 年过的《管理》成绩，今年实务不过就要作废重考",
});
assert.ok(personalized.personalization.indexOf("作废重考") >= 0);

// ── 8. 文案红线扫描(§4.2 禁语 + §4.3 语气 + §8.3 禁「挂靠」) ──
var forbidden = [
  "挂靠",
  "看穿",
  "破绽",
  "保证过线",
  "准确预测",
  "百万考生",
  "超过全国",
  "AI批改准确率",
];
var sources = [
  vmPath,
  path.join(__dirname, "../packageDeeptutor/utils/pass-readiness-view-model.js"),
];
var pageRoot = path.join(__dirname, "../packageDeeptutor/pages/luban/pass-readiness");
if (fs.existsSync(pageRoot)) {
  fs.readdirSync(pageRoot).forEach(function (dir) {
    var full = path.join(pageRoot, dir);
    if (!fs.statSync(full).isDirectory()) return;
    fs.readdirSync(full).forEach(function (file) {
      if (/\.(js|wxml)$/.test(file)) sources.push(path.join(full, file));
    });
  });
}
sources.forEach(function (file) {
  var text = fs.readFileSync(file, "utf8");
  forbidden.forEach(function (word) {
    assert.strictEqual(
      text.indexOf(word),
      -1,
      path.basename(file) + " 含禁语: " + word,
    );
  });
});

console.log("PASS test_pass_readiness_report_view_model.js");
