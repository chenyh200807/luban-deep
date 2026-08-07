// Run: node yousenwebview/tests/test_pass_readiness_report_view_model.js
// 过线体检结果侧视图模型域测试(C 线契约版):
// 1. report.pass_readiness 块投影(band_status/band_lower/band_upper/band_tier/
//    pass_line/ability_readiness/prep_feasibility/risk_band/coverage/interval/
//    unmeasured_dimensions/self_reported_score_label);
// 2. band_status=evidence_insufficient → 诚实空态(band_copy 分支), 不造分数带;
// 3. coverage=low 时 reference_pass_interval 空串 → 不渲染;
// 4. 首屏精确整数纪律: 精确就绪度只出现在 ability_readiness_detail(证据详情屏);
// 5. unmeasured_dimensions 含 answer_expression → 禁表达弱点表述;
// 6. 证据屏槽位 + 易错点空槽诚实占位 + 绑定缺失禁 dead button + wrong_items 兜底;
// 7. 计划预览 loading 态零假数据; 收据文案逐字; 保存/会员文案红线;
// 8. /assessment/profile diagnostic_sources.pass_readiness 唯一判断源。
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var vmPath = path.join(
  __dirname,
  "../packageDeeptutor/utils/pass-readiness-report-view-model.js",
);
var vm = require(vmPath);

// ── 1. pass_readiness 块投影 ─────────────────────────────────
var report = {
  schema_version: "p0a-v1",
  score_summary: { scored_count: 12, correct_count: 7 },
  wrong_items: [],
  pass_readiness: {
    band_status: "ok",
    estimated_score_band: "100–125 分",
    band_lower: 100,
    band_upper: 125,
    band_width: 25,
    band_tier: "default",
    pass_line: 96,
    ability_readiness: "中高 (75–85)",
    ability_readiness_detail: "78 / 100（model_version band-v1）",
    prep_feasibility: "时间预算偏紧",
    risk_band: "临界不稳",
    evidence_coverage: "medium",
    band_policy_version: "band-v1",
    reference_pass_interval: "45%–60%",
    unmeasured_dimensions: ["answer_expression"],
    self_reported_score_label: "自报未核验",
    diagnosis: "主要失分集中在案例采分点检索，而且马上能补。",
  },
};
var result = vm.buildResultModel(report);
assert.strictEqual(result.bandAvailable, true);
assert.strictEqual(result.bandText, "100–125 分");
assert.strictEqual(result.bandTier, "default");
assert.strictEqual(result.passLine, 96);
assert.strictEqual(result.passLineLabel, "过线 96 分");
assert.strictEqual(result.riskBand, "临界不稳");
assert.strictEqual(
  result.riskLine,
  "临界不稳 · 时间预算偏紧",
  "prep_feasibility 独立字段只拼进风险措辞",
);
assert.strictEqual(result.readinessTier, "中高");
assert.strictEqual(result.readinessRange, "75–85");
assert.strictEqual(result.evidenceCoverageLabel, "中");
assert.strictEqual(result.bandPolicyVersion, "band-v1");
assert.strictEqual(result.showReferenceInterval, true);
assert.strictEqual(result.referencePassInterval, "45%–60%");
assert.strictEqual(result.selfReportedScoreLabel, "自报未核验");
assert.strictEqual(result.expressionMeasured, false, "unmeasured 含 answer_expression");
// CTA 说清目的地(owner 2026-08-07:原文案看不出点进去有什么)。
// 本 fixture 无失分证据 → 回落通用式;有证据时带数量,见下方断言。
assert.strictEqual(result.primaryCta, "看我的采分点证据");
// 几何/差距用 band_lower/band_upper 数值字段, 不靠解析展示串
assert.ok(result.geometry && result.geometry.passLinePct < 100);
assert.strictEqual(
  result.gapLine,
  "预估分数带已越过过线线——用复测把它坐实",
  "band_lower 高于过线线 → 不出差 X 分, 改为复测坐实框架",
);
assert.ok(result.geometry.bandLeftPct > result.geometry.passLinePct - 20);
assert.ok(
  result.disclaimer.indexOf("尚未经过真实考试结果校准") >= 0,
  "信任声明必须逐字保留未校准边界",
);

// 带在过线线下方 → 损失框架句
var below = vm.buildResultModel({
  pass_readiness: {
    band_status: "ok",
    estimated_score_band: "75–95 分",
    band_lower: 75,
    band_upper: 95,
    pass_line: 96,
  },
});
assert.strictEqual(below.gapLine, "离过线还差最多 21 分", "gap = pass_line − band_lower");

// ── 2. 证据不足分支(band_copy) ───────────────────────────────
var insufficient = vm.buildResultModel({
  pass_readiness: {
    band_status: "evidence_insufficient",
    estimated_score_band: null,
    band_copy: "evidence insufficient for a band",
    pass_line: 96,
    evidence_coverage: "low",
    reference_pass_interval: "",
  },
});
assert.strictEqual(insufficient.bandAvailable, false);
assert.strictEqual(insufficient.bandText, "");
assert.strictEqual(insufficient.geometry, null, "无带不画带");
assert.strictEqual(insufficient.gapLine, "");
assert.strictEqual(
  insufficient.bandUnavailableCopy,
  "evidence insufficient for a band",
  "空态优先用服务端 band_copy",
);
// ── 3. low 档 interval 空串不渲染 ────────────────────────────
assert.strictEqual(insufficient.showReferenceInterval, false);

// ── 4. 首屏精确整数纪律 ──────────────────────────────────────
assert.strictEqual(typeof result.readinessTier, "string");
assert.strictEqual(typeof result.readinessRange, "string");
Object.keys(result).forEach(function (key) {
  if (key === "passLine") return; // 过线线 96 是契约常量, 允许
  assert.ok(
    !(typeof result[key] === "number" && key.toLowerCase().indexOf("readiness") >= 0),
    "首屏模型禁出精确整数就绪度字段: " + key,
  );
});
assert.ok(
  !("abilityReadinessDetail" in result) && !("readinessDetail" in result),
  "精确就绪度不进首屏模型",
);
var detail = vm.buildReadinessDetail(report);
assert.strictEqual(detail.available, true);
assert.ok(detail.text.indexOf("78") >= 0, "精确值只在证据详情屏投影");

// ── 5/6. 证据屏 ──────────────────────────────────────────────
var evidence = vm.buildEvidenceModel(
  {
    pass_readiness: report.pass_readiness,
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
        why_missed: "表达不完整导致失分。",
        source: "教材 2026 版",
      },
    ],
  },
  result,
);
assert.strictEqual(evidence.items.length, 2);
assert.strictEqual(evidence.isEmpty, false);
assert.strictEqual(evidence.items[0].pitfallAvailable, true);
assert.strictEqual(evidence.items[1].pitfallAvailable, false);
assert.strictEqual(
  evidence.items[1].pitfall,
  "该采分点的易错点整理中",
  "易错点空槽必须诚实占位而非伪造",
);
assert.strictEqual(
  evidence.items[1].whyMissed,
  "",
  "answer_expression 未测时禁出表达失分归因",
);
assert.strictEqual(evidence.items[0].lessonPackId, "F16");
assert.strictEqual(
  evidence.items[1].lessonPackId,
  "",
  "无绑定则空 → 页面不渲染按钮(禁 dead button)",
);
// 微课未绑定 → 卡片不再挂「整理中」待办占位(owner 2026-08-07):
// §7.6 的禁 dead button 由按钮条件渲染满足,不需要额外的自家 backlog 文案。
assert.ok(evidence.lessonCta.length > 0);
assert.strictEqual(evidence.readinessDetail.available, true, "精确就绪度挂在证据详情模型");

// p0a wrong_items 兜底(错题渲染复用既有链字段)
var fallbackEvidence = vm.buildEvidenceModel(
  {
    wrong_items: [
      {
        question_stem: "错题题干",
        learner_answer: "C",
        knowledge_points: ["主体结构"],
        simple_explanation: "这题考完整枚举。",
      },
    ],
  },
  null,
);
assert.strictEqual(fallbackEvidence.items.length, 1);
assert.strictEqual(fallbackEvidence.items[0].scoringPoint, "主体结构");
assert.strictEqual(fallbackEvidence.items[0].whyMissed, "这题考完整枚举。");

// ── 7. 计划预览(exam-prep-plan 冻结形状) ─────────────────────
var pendingPlan = vm.buildPlanPreviewModel(null);
assert.strictEqual(pendingPlan.status, "pending");
assert.strictEqual(pendingPlan.items.length, 0, "loading 态零假数据");
assert.strictEqual(pendingPlan.slots.length, 3, "三优先静态结构槽");
pendingPlan.slots.forEach(function (slot) {
  assert.ok(!slot.cta && !slot.url, "loading 态禁假按钮");
});
// enabled:false → 即使带 days 也保持骨架(旗标权威在服务端)
var disabledPlan = vm.buildPlanPreviewModel({
  enabled: false,
  days: [{ date: "2026-08-06", tasks: [{ task: "不该出现", why: "x" }] }],
});
assert.strictEqual(disabledPlan.status, "pending", "enabled:false 必须保持骨架");
assert.strictEqual(disabledPlan.items.length, 0);
// enabled 投影: 全 days 拍平取前三, 映射 task/why/expected_time
var readyPlan = vm.buildPlanPreviewModel({
  enabled: true,
  exam_countdown_days: 92,
  days: [
    {
      date: "2026-08-06",
      tasks: [
        { task: "补模板拆除采分点", why: "本次诊断最大失分点", expected_time: "10 分钟", mode: "lesson", target_pack_id: "F16" },
        { task: "平行复测同一采分点", why: "拿一次新的正面证据", expected_time: "5 分钟", mode: "retest", target_pack_id: "F16" },
      ],
    },
    {
      date: "2026-08-07",
      tasks: [
        { task: "网络计划轻练", why: "第二失分风险", expected_time: "8 分钟", mode: "practice" },
        { task: "溢出任务", why: "不该进前三", expected_time: "1 分钟" },
      ],
    },
  ],
});
assert.strictEqual(readyPlan.status, "ready");
assert.strictEqual(readyPlan.items.length, 3, "全 days 拍平后只取前三");
assert.strictEqual(readyPlan.items[0].title, "补模板拆除采分点");
assert.strictEqual(readyPlan.items[0].desc, "本次诊断最大失分点");
assert.strictEqual(readyPlan.items[0].expectedTime, "10 分钟");
assert.strictEqual(readyPlan.items[0].targetPackId, "F16");
assert.strictEqual(readyPlan.items[2].title, "网络计划轻练", "跨天拍平次序保持");
assert.strictEqual(
  readyPlan.items.filter(function (item) { return item.title === "溢出任务"; }).length,
  0,
);
// 空 days → 骨架
assert.strictEqual(vm.buildPlanPreviewModel({ enabled: true, days: [] }).status, "pending");

// ── 收据 / 保存 / 会员 ───────────────────────────────────────
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

// ── 8. diagnostic_sources.pass_readiness 唯一判断源 ──────────
var source = vm.readDiagnosticSource({
  data: {
    diagnostic_sources: {
      pass_readiness: { completed: true, quiz_id: "quiz_pr_9", scored_at: "2026-08-05T10:00:00Z" },
    },
  },
});
assert.strictEqual(source.completed, true);
assert.strictEqual(source.quizId, "quiz_pr_9");
assert.strictEqual(source.scoredAt, "2026-08-05T10:00:00Z");
var emptySource = vm.readDiagnosticSource({});
assert.strictEqual(emptySource.completed, false, "缺块 = 未完成, 不由前端自判");

// ── 9. 文案红线扫描(§4.2 禁语 + §4.3 语气 + §8.3 红线词) ─────
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

// ── 首屏「接下来你会看到」预告(owner 2026-08-07:首屏没有继续下去的理由) ──
// 只点名报告里已定位的采分点,数量与点名全部来自报告——零编造。
var previewReport = {
  schema_version: "pass-readiness-v1",
  pass_readiness: {
    estimated_score_band: "70–90 分",
    band_lower: 70,
    band_upper: 90,
    pass_line: 96,
    evidence_items: [
      { question_stem: "题一", scoring_point: "施工缝·处理工序" },
      { question_stem: "题二", scoring_point: "拆模·强度条件" },
      { question_stem: "题三", scoring_point: "钢筋接头·位置" },
      { question_stem: "题四", scoring_point: "进度·关键线路" },
    ],
  },
};
var previewResult = vm.buildResultModel(previewReport);
assert.strictEqual(previewResult.nextPreview.available, true);
assert.strictEqual(previewResult.nextPreview.count, 4);
assert.deepStrictEqual(previewResult.nextPreview.points, [
  "施工缝·处理工序",
  "拆模·强度条件",
  "钢筋接头·位置",
]);
assert.strictEqual(previewResult.nextPreview.moreCount, 1, "超出 3 个只提示数量,不铺满首屏");
assert.strictEqual(
  previewResult.primaryCta,
  "看这 4 个失分点怎么补回来",
  "CTA 必须说清点进去看到什么 + 用真实数量",
);

// 零证据时预告整块不渲染(不摆空架子)
var emptyPreview = vm.buildResultModel({
  schema_version: "pass-readiness-v1",
  pass_readiness: { estimated_score_band: "70–90 分", pass_line: 96 },
});
assert.strictEqual(emptyPreview.nextPreview.available, false);

console.log("PASS test_pass_readiness_report_view_model.js");
