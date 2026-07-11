// Run: node yousenwebview/tests/test_gauntlet_view_model.js
// 实务闯关(回忆→半写→核对)域测试:
// 1. 题面 = 变体池 read model 原样投影(不造新供给); ①回忆采分点只露数量;
// 2. ③核对 = retest 同款本地确定性判分(choice === expected_ok, 唯一机制);
// 3. ②半写 R6 挖空无供给 → 自由默写如实降级(禁伪装挖空, 禁造「已记进」声明);
// 4. 零学情写入(源码钉死) + 只用已登记埋点名; 草稿形状; 复习页接线 fail-closed;
// 5. 文案铁律禁词 + WXML 平衡 + 注册。
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var vmPath = path.join(__dirname, "../packageDeeptutor/utils/gauntlet-view-model.js");
var vm = require(vmPath);

// ── 1. 题面投影 + 采分点只露数量 ─────────────────────────────
var built = vm.buildGauntletViewModel({
  items: [
    {
      variant_id: "v1",
      rule_group: "claim",
      surface: "监理人未在 7 天内答复即视为认可",
      expected_ok: false,
      correct_statement: "正确说法示意",
      anchor: "教材 · 合同与索赔章节",
    },
    { variant_id: "v2", surface: "另一条做法", expected_ok: true },
  ],
});
assert.strictEqual(built.total, 2);
assert.strictEqual(built.isEmpty, false);
assert.strictEqual(built.items[0].key, "v1");
assert.strictEqual(built.items[0].expected_ok, false);
assert.strictEqual(built.items[0].answered, false);
assert.ok(built.pointCountLine.indexOf("2 个判断点") >= 0, "①回忆只露数量");
assert.strictEqual(built.pointCountLine.indexOf("正确说法示意"), -1, "①回忆禁露答案内容");

// 空供给: 诚实空态, 不造题
var emptyBuilt = vm.buildGauntletViewModel({});
assert.strictEqual(emptyBuilt.isEmpty, true);
assert.strictEqual(emptyBuilt.total, 0);
assert.strictEqual(emptyBuilt.pointCountLine, "");

// ── 2. 本地确定性判分(retest 同款唯一机制) ────────────────────
assert.strictEqual(vm.gradeChoice({ expected_ok: false }, false), true, "选不妥 × 期望不妥 = 命中");
assert.strictEqual(vm.gradeChoice({ expected_ok: false }, true), false);
assert.strictEqual(vm.gradeChoice({ expected_ok: true }, true), true);
assert.strictEqual(vm.gradeChoice({ expected_ok: true }, false), false);

// ── 3. 结果投影(呈现层, 零掌握结论) ──────────────────────────
var verdictAll = vm.buildVerdict([
  { answered: true, correct: true },
  { answered: true, correct: true },
]);
assert.strictEqual(verdictAll.done, true);
assert.strictEqual(verdictAll.hitLabel, "2/2");
assert.strictEqual(verdictAll.percent, 100);
assert.ok(verdictAll.heroTitle.indexOf("全部命中") >= 0);

var verdictMissOne = vm.buildVerdict([
  { answered: true, correct: true },
  { answered: true, correct: true },
  { answered: true, correct: true },
  { answered: true, correct: false },
]);
assert.ok(verdictMissOne.heroTitle.indexOf("就差一步") >= 0, "漏 1 条 = 暖标题");
assert.strictEqual(verdictMissOne.hitCount, 3);

var verdictPartial = vm.buildVerdict([
  { answered: true, correct: true },
  { answered: false, correct: null },
]);
assert.strictEqual(verdictPartial.done, false, "未答完不出终局");

// ── 4. 草稿形状(退出留草稿承诺的唯一载体) ─────────────────────
var draft = vm.buildDraft("  不可抗力 · 关键线路  ", 2);
assert.strictEqual(draft.text, "不可抗力 · 关键线路");
assert.strictEqual(draft.step, 2);
assert.ok(draft.savedAt > 0);
assert.strictEqual(vm.buildDraft("x", 3).step, 2, "③核对不落草稿, step 封顶 2");
assert.strictEqual(vm.buildDraft("x", 0).step, 1);
assert.strictEqual(vm.draftStorageKey("f16"), "luban_gauntlet_draft:F16");

// ── 5. 红线源码钉死: 零学情写入 + 只用已登记埋点 ──────────────
var pageDir = path.join(__dirname, "../packageDeeptutor/pages/luban/gauntlet");
var pageJs = fs.readFileSync(path.join(pageDir, "gauntlet.js"), "utf8");
var pageWxml = fs.readFileSync(path.join(pageDir, "gauntlet.wxml"), "utf8");
var pageWxss = fs.readFileSync(path.join(pageDir, "gauntlet.wxss"), "utf8");
var vmSource = fs.readFileSync(vmPath, "utf8");
assert.strictEqual(pageJs.indexOf("markMistakeBookItemMastered"), -1, "闯关禁写 mastered 旗标");
assert.strictEqual(pageJs.indexOf("saveMistakeBookItem"), -1, "闯关禁前端造错因记账(记账真值=判分内核 writeback)");
assert.ok(pageJs.indexOf("postStationCompleted") >= 0, "完成只发既有非 promoting 站完成信号");
// 埋点只用 D15 已登记名(register-before-use), 禁自由 luban_* 事件名
assert.ok(pageJs.indexOf('"retest_item_answered"') >= 0, "变体作答复用已登记事件名");
assert.ok(pageJs.indexOf('"learning_action_completed"') >= 0, "完成复用已登记事件名");
assert.ok(!/trackProductBehavior\(\s*"luban_/.test(pageJs), "禁未登记 luban_* 自由事件名");
// 漏点反馈禁造「已记进错因银行」——前端无记账签发权, 文案不许假声明
assert.strictEqual(pageWxml.indexOf("已记进错因银行"), -1, "漏点文案禁假声明记账(记账只归判分内核)");
// ②半写如实降级: 页面明说挖空在准备中, 不伪装精确挖空
assert.ok(pageWxml.indexOf("精确挖空练习正在准备中") >= 0, "半写降级必须如实标注");
// R6 挖空 bank 接口位形状留在 vm 头注(供后续内容管线对接)
assert.ok(vmSource.indexOf("skeleton_sentences") >= 0, "R6 挖空 bank 接口位形状须在 vm 注释钉死");
// 退出挽留: 主按钮给退出(保留草稿), 继续作答是 ghost
assert.ok(pageWxml.indexOf("保留草稿 · 先退出") >= 0);
assert.ok(pageWxml.indexOf("继续作答") >= 0);
var primaryIdx = pageWxml.indexOf("保留草稿 · 先退出");
var sheetBtnClass = pageWxml.slice(pageWxml.lastIndexOf("<view", primaryIdx), primaryIdx);
assert.ok(sheetBtnClass.indexOf("gt-btn") >= 0, "sheet 主按钮(墨色)必须给退出, 不做暗黑挽留");

// ── 5b. 档位③全量作答(判分内核 seam 投影) ────────────────────
// 前端零判分: status / score 全部原样透传内核, vm 只做呈现映射。
var faL0 = vm.buildFullAnswerVerdict({
  scoring_points: [
    { criterion: "判断监理答复时限", status: "full", awarded_score: 1, max_score: 1 },
    { criterion: "援引合同条款依据", status: "miss", awarded_score: 0, max_score: 1 },
    { criterion: "结论表述完整", status: "partial", awarded_score: 0.5, max_score: 1 },
  ],
  score_awarded: 1.5,
  max_score: 3,
  evidence_level: "L0_observed",
  stable_truth_eligible: false,
  writeback_count: 2,
});
assert.strictEqual(faL0.graded, true);
assert.strictEqual(faL0.scoreLine, "1.5 / 3");
assert.strictEqual(faL0.points[0].chipClass, "grn", "命中→竹青绿");
assert.strictEqual(faL0.points[1].chipClass, "och", "漏点→赭暖");
assert.strictEqual(faL0.points[2].chipClass, "line", "部分命中→中性");
assert.strictEqual(faL0.missCount, 1);
assert.strictEqual(faL0.hasPoints, true);
// 诚实封顶: L0 不假装稳定掌握, 如实告知升级路径
assert.strictEqual(faL0.stableEligible, false);
assert.ok(faL0.capNote.indexOf("升级") >= 0 && faL0.capNote.indexOf("稳定掌握") >= 0, "L0 如实说待升级, 不假装满分掌握");
// 有漏点 + 后端确有 writeback → 如实转述入错因银行(记账真值归内核)
assert.ok(faL0.mistakeNote.indexOf("错因银行") >= 0, "漏点+后端写入→如实转述记账");
// 剥离键: verdict 不得回传 keywords / required_terms(防再认泄漏)
assert.strictEqual(faL0.points[0].keywords, undefined);
assert.strictEqual(faL0.points[0].required_terms, undefined);

// 后端无写入 → 前端绝不假声明记账
var faNoWrite = vm.buildFullAnswerVerdict({
  scoring_points: [{ criterion: "x", status: "miss", awarded_score: 0, max_score: 1 }],
  writeback_count: 0,
  stable_truth_eligible: false,
});
assert.strictEqual(faNoWrite.mistakeNote, "", "后端无 writeback→前端不假声明记账");

// stable 掌握路径(权威采分点已签发)
var faStable = vm.buildFullAnswerVerdict({
  scoring_points: [{ criterion: "x", status: "full", awarded_score: 1, max_score: 1 }],
  score_awarded: 1,
  max_score: 1,
  evidence_level: "L2_curated",
  stable_truth_eligible: true,
  writeback_count: 0,
});
assert.strictEqual(faStable.stableEligible, true);
assert.ok(faStable.capNote.indexOf("稳定掌握") >= 0);

// open_skill(无签发采分点): 空清单如实, 不列空点充数, 默认 L0
var faOpen = vm.buildFullAnswerVerdict({ scoring_points: [] });
assert.strictEqual(faOpen.hasPoints, false);
assert.strictEqual(faOpen.points.length, 0);
assert.strictEqual(faOpen.evidenceLevel, "L0_observed", "缺 evidence_level 默认 L0(保守)");
assert.strictEqual(faOpen.stableEligible, false);

// 页面红线: 前端只投递 variant_id/answer_text, 零本地判分, fail-closed 不伪造
assert.ok(pageJs.indexOf("postLubanFullAnswer") >= 0, "全量作答走既有 seam api, 前端不新造判分");
assert.ok(pageJs.indexOf("buildFullAnswerVerdict") >= 0, "verdict 由 vm 投影, 前端不自算分");
assert.strictEqual(pageJs.indexOf("required_terms"), -1, "页面禁持有 required_terms(防再认泄漏+禁本地判分)");
assert.strictEqual(pageJs.indexOf("keywords"), -1, "页面禁持有 keywords(防再认泄漏)");
assert.ok(pageJs.indexOf("statusCode === 404") >= 0, "旗标关/未签发→404 fail-closed 分支");
assert.ok(pageJs.indexOf("即将开通") >= 0, "fail-closed 诚实占位, 绝不本地伪造判分");
// 输入期(②半写 textarea)禁把采分点做候选词/提示(D16)
assert.strictEqual(pageWxml.indexOf("required_terms"), -1, "WXML 禁注入 required_terms 候选词");
assert.ok(pageWxml.indexOf("gt-fa-cap") >= 0, "全量作答 L0 封顶披露位存在");
// api 方法契约: 端点路径 + 只两个投递键
var apiSource = fs.readFileSync(path.join(__dirname, "../packageDeeptutor/utils/api.js"), "utf8");
assert.ok(apiSource.indexOf("postLubanFullAnswer") >= 0 && /full-answer/.test(apiSource), "seam 端点已接线");
assert.ok(apiSource.indexOf("postLubanFullAnswer: postLubanFullAnswer") >= 0, "seam api 已导出");
// 轻档不变: ②默写/①填空仍走本地(非 promoting), 全量作答是独立加档
assert.ok(pageJs.indexOf("startVerify") >= 0 && pageJs.indexOf("onChoiceTap") >= 0, "本地核对轻档保持(轻练不关闭弱点)");

// ── 6. 复习页接线: 入口 fail-closed + 单一判定点 ──────────────
var reviewVm = require(path.join(__dirname, "../packageDeeptutor/utils/review-view-model.js"));
var reviewBuilt = reviewVm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }, { pack_id: "A01", title: "检验批" }] },
  reviewDue: {
    due: [
      { pack_id: "F16", title: "屋面防水", retest_available: true },
      { pack_id: "A01", title: "检验批", retest_available: false },
    ],
    learned_count: 2,
  },
});
assert.strictEqual(reviewBuilt.dueEntries[0].gauntletAvailable, true, "有变体池→闯关入口开");
assert.strictEqual(reviewBuilt.dueEntries[1].gauntletAvailable, false, "无池站 fail-closed 不给闯关入口(题面/判分都吃变体池)");
var reviewWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/review/review.wxml"), "utf8");
assert.ok(reviewWxml.indexOf('wx:if="{{item.gauntletAvailable}}"') >= 0, "复习页闯关入口须由 vm 单一判定点控制");
assert.ok(reviewWxml.indexOf('catchtap="openGauntlet"') >= 0, "到期清单行挂实务闯关入口");
var reviewJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/review/review.js"), "utf8");
assert.ok(reviewJs.indexOf("route.lubanGauntlet(") >= 0, "闯关路由走 route 单一权威");

// ── 7. 文案铁律: 禁审视揭短词 ─────────────────────────────────
var FORBIDDEN = ["看穿", "识破", "揭穿", "露馅", "拆穿"];
[
  ["gauntlet-view-model.js", vmSource],
  ["gauntlet.js", pageJs],
  ["gauntlet.wxml", pageWxml],
  ["gauntlet.wxss", pageWxss],
].forEach(function (pair) {
  FORBIDDEN.forEach(function (word) {
    assert.strictEqual(pair[1].indexOf(word), -1, pair[0] + " 含禁词「" + word + "」");
  });
});

// ── 8. WXML 标签平衡(自闭合感知) ─────────────────────────────
function checkWxmlBalance(source) {
  var src = source.replace(/<!--[\s\S]*?-->/g, "").replace(/<wxs[\s\S]*?<\/wxs>/g, "");
  var re = /<(\/?)([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^><"'])*)>/g;
  var stack = [];
  var match;
  while ((match = re.exec(src))) {
    var closing = match[1] === "/";
    var name = match[2];
    var attrs = match[3] || "";
    if (attrs.replace(/\s+$/, "").slice(-1) === "/") continue;
    if (closing) {
      if (!stack.length || stack[stack.length - 1] !== name) {
        return "mismatched </" + name + ">";
      }
      stack.pop();
    } else {
      stack.push(name);
    }
  }
  return stack.length ? "unclosed: " + stack.join(",") : "";
}
assert.strictEqual(checkWxmlBalance(pageWxml), "", "gauntlet.wxml 标签必须平衡: " + checkWxmlBalance(pageWxml));
assert.strictEqual(checkWxmlBalance(reviewWxml), "", "review.wxml 接线后标签必须平衡");

// ── 9. 注册 ──────────────────────────────────────────────────
var appConfig = fs.readFileSync(path.join(__dirname, "../app.json"), "utf8");
assert.ok(appConfig.indexOf("pages/luban/gauntlet/gauntlet") >= 0, "app.json 须注册实务闯关页");

// ── 10. ②半写 · R6 精确挖空(供给上线正式形态) ──────────────
var buildClozeViewModel = vm.buildClozeViewModel;
var gradeClozeBlank = vm.gradeClozeBlank;
// 正常供给 → available + 行投影
var cz = buildClozeViewModel({
  recall_prompt: "想一想：关键词能默写全吗？",
  skeleton_sentences: [
    { cloze_id: "A01:C1-1", point_id: "kc:x:1", text_before: "验收四级体系：", blank_hint: "检验批 / 单位工程", text_after: "" },
    { cloze_id: "A01:C1-2", point_id: "kc:x:2", text_before: "先", blank_hint: "自检", text_after: "再报验" },
    { text_before: "无提示行", blank_hint: "", text_after: "(应被剔除)" },
  ],
});
assert.strictEqual(cz.available, true);
assert.strictEqual(cz.total, 2, "无 blank_hint 的行保守剔除");
assert.strictEqual(cz.sentences[0].hint, "检验批 / 单位工程");
assert.strictEqual(cz.sentences[0].checked, false);
// 缺供给/畸形 → available=false(页面保持自由默写降级)
assert.strictEqual(buildClozeViewModel(null).available, false);
assert.strictEqual(buildClozeViewModel({ skeleton_sentences: [] }).available, false);
// 自查确定性: 多候选词(/、分隔)互相包含命中; <2字/空输入不命中
assert.strictEqual(gradeClozeBlank("检验批 / 单位工程", "检验批"), true);
assert.strictEqual(gradeClozeBlank("检验批 / 单位工程", "单位工程验收"), true, "输入包含候选词=命中");
assert.strictEqual(gradeClozeBlank("检验批 / 单位工程", "检"), false, "单字防误中");
assert.strictEqual(gradeClozeBlank("检验批 / 单位工程", ""), false);
assert.strictEqual(gradeClozeBlank("检验批 / 单位工程", "隐蔽工程"), false);
assert.strictEqual(gradeClozeBlank("自检", "先自检再报"), true);
// 页面接线: wxml 含挖空区且保留降级注记(仅无供给时)
assert.ok(pageWxml.indexOf("gt-cloze-row") >= 0, "gauntlet.wxml 须渲染挖空行");
assert.ok(pageWxml.indexOf('wx:if="{{!cloze}}"') >= 0, "降级注记只在无 cloze 供给时渲染");
var pageJs = fs.readFileSync(path.join(__dirname, "../packageDeeptutor/pages/luban/gauntlet/gauntlet.js"), "utf8");
assert.ok(pageJs.indexOf("getLubanCloze") >= 0, "gauntlet.js 须真消费 cloze 端点(死供给转活)");

console.log("PASS test_gauntlet_view_model.js");
