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

console.log("PASS test_gauntlet_view_model.js");
