// Run: node yousenwebview/tests/test_review_view_model.js
// 复习页(10c 回炉屏)视图模型域测试:
// 1. 到期语义只来自服务端 review-due 投影(前端零调度零探测);
// 2. 变体池空的站 fail-closed 隐藏「换皮」承诺句;
// 3. 文案铁律: 复习面禁审视揭短词(帮你变强基调);
// 4. 回归防线: review 页源码禁止 N+1 retest-items 探测(假'有池=到期')。
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var vmPath = path.join(__dirname, "../packageDeeptutor/utils/review-view-model.js");
var vm = require(vmPath);

// ── 1. 正常到期投影 ───────────────────────────────────────────
var built = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }, { pack_id: "A01", title: "检验批" }] },
  reviewDue: {
    due: [
      { pack_id: "F16", title: "屋面防水", probe_id: "rvp_f16", due_at: "2026-07-04T00:00:00+08:00", retest_available: true },
      { pack_id: "A01", title: "检验批", due_at: "2026-07-04T00:00:00+08:00", retest_available: false },
    ],
    learned_count: 2,
    authority: "revalidation_queue",
    enabled: true,
  },
  mistakeBook: { activeCount: 3, errorBars: [{ key: "E03", label: "关键词缺失", count: 2 }] },
});
assert.strictEqual(built.dueCount, 2);
assert.strictEqual(built.learnedCount, 2);
assert.strictEqual(built.duePercent, 100);
assert.strictEqual(built.mistakeActiveCount, 3);
assert.strictEqual(built.isEmpty, false);
assert.strictEqual(built.firstDue.packId, "F16");
assert.strictEqual(built.firstDue.probeId, "rvp_f16");
assert.strictEqual(built.showPact, true, "首个到期站有变体池→渲染约定卡");

// ── 2. fail-closed: 换皮承诺句只出现在有变体池的条目 ──────────
var withPool = built.dueEntries[0];
var withoutPool = built.dueEntries[1];
assert.strictEqual(withPool.action, "retest");
assert.ok(withPool.sub.indexOf("换皮") >= 0, "有池条目带换皮承诺");
assert.strictEqual(withoutPool.action, "station", "无池条目降级为回站重看");
assert.strictEqual(withoutPool.sub.indexOf("换皮"), -1, "无池条目禁换皮承诺句(fail-closed)");
assert.strictEqual(withoutPool.retestAvailable, false);

// 首个到期站无池 → 约定卡整卡不渲染
var noPoolFirst = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "A01", title: "检验批" }] },
  reviewDue: { due: [{ pack_id: "A01", title: "检验批", retest_available: false }], learned_count: 1 },
});
assert.strictEqual(noPoolFirst.showPact, false, "首个到期站无池→换皮约定卡 fail-closed 不渲染");

// ── 3. 空态与降级(后端旗标关/未部署: 不抛不崩, 诚实空态) ────────
var empty = vm.buildReviewViewModel({});
assert.strictEqual(empty.isEmpty, false);
assert.strictEqual(empty.reviewState, "unavailable");
assert.strictEqual(empty.dueCount, 0);
assert.strictEqual(empty.duePercent, 0);
assert.strictEqual(empty.showPact, false);
assert.strictEqual(empty.mistakeActiveCount, -1, "错题计数未取到=-1(降级为无计数,不造数)");
assert.deepStrictEqual(empty.errorBars, []);

var flagOff = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }] },
  reviewDue: { due: [], learned_count: 0, enabled: false },
  mistakeBook: null,
});
assert.strictEqual(flagOff.isEmpty, false, "旗标关必须显示 disabled，不冒充无历史或全部稳定");
assert.strictEqual(flagOff.reviewState, "disabled");
assert.strictEqual(flagOff.dueCount, 0);

var noHistory = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }] },
  reviewDue: { due: [], learned_count: 0, enabled: true, authority: "revalidation_queue" },
});
assert.strictEqual(noHistory.isEmpty, true);
assert.strictEqual(noHistory.reviewState, "no_history");

var allClear = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }] },
  reviewDue: { due: [], learned_count: 1, enabled: true, authority: "revalidation_queue" },
});
assert.strictEqual(allClear.reviewState, "all_clear");

var degraded = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }] },
  reviewDue: {
    due: [],
    learned_count: 0,
    enabled: null,
    degraded: true,
    authority: "revalidation_queue",
  },
});
assert.strictEqual(degraded.reviewState, "unavailable", "降级态不得被 authority 字符串伪装成无历史");
assert.strictEqual(degraded.isEmpty, false);

// ── 3.5 点亮语义(问题2回归): 绿灯(published)≠点亮(learned) ─────
// 点亮真值 = pack_lifecycle（与学习页同一 lit 判定, 单一权威）;
// 绿灯只是可学, 未点亮站显示中性态, 禁把 28 个绿灯站全标「已点亮」。
var litBuilt = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }, { pack_id: "A01", title: "检验批" }] },
  reviewDue: { due: [], learned_count: 1 },
  report: {
    pack_lifecycle: {
      packs: {
        F16: { lifecycle_state: "practiced" },
        A01: { lifecycle_state: "unlearned" },
      },
    },
  },
});
var litRow = litBuilt.lessons.filter(function (l) { return l.pack_id === "F16"; })[0];
var unlitRow = litBuilt.lessons.filter(function (l) { return l.pack_id === "A01"; })[0];
assert.strictEqual(litRow.lit, true, "practiced 站=点亮");
assert.ok(litRow.sub.indexOf("已点亮") >= 0, "点亮站保留回站重看文案");
assert.strictEqual(unlitRow.lit, false, "unlearned 站≠点亮");
assert.strictEqual(unlitRow.sub.indexOf("已点亮"), -1, "未点亮站禁标已点亮(语义与学习页一致)");
assert.ok(unlitRow.sub.length > 0, "未点亮站给中性态文案");

// exposed(只看过讲懂, M0 蓝环)与学习页口径一致: 不算点亮
var exposedBuilt = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }] },
  reviewDue: { due: [], learned_count: 1 },
  report: { pack_lifecycle: { packs: { F16: { lifecycle_state: "exposed" } } } },
});
assert.strictEqual(exposedBuilt.lessons[0].lit, false, "exposed 不算点亮(M0: 看动画不算掌握)");

// lifecycle 不可用(旧后端/接口失败)→ 不造数: 既不标已点亮也不标未开始
var noLifecycle = vm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "F16", title: "屋面防水" }] },
  reviewDue: { due: [], learned_count: 0 },
});
assert.strictEqual(noLifecycle.lessons[0].lit, false);
assert.strictEqual(noLifecycle.lessons[0].sub.indexOf("已点亮"), -1, "lifecycle 缺失时禁自造点亮态");
assert.strictEqual(noLifecycle.lessons[0].sub.indexOf("未点亮"), -1, "lifecycle 缺失时也禁断言未点亮(不造数)");

// 单一 lit 判定权威: review-view-model 必须复用 learn-view-model 的判定, wxml 禁硬编码点亮文案
var vmSource = fs.readFileSync(vmPath, "utf8");
assert.ok(
  vmSource.indexOf("learn-view-model") >= 0 && vmSource.indexOf("isLitLifecycleState") >= 0,
  "review-view-model 必须复用 learn-view-model 的 isLitLifecycleState(禁第二套点亮判定)",
);
var reviewWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/review/review.wxml"), "utf8");
assert.strictEqual(reviewWxml.indexOf("已点亮"), -1, "wxml 禁硬编码「已点亮」——点亮态只来自 view model");

// ── 4. 文案铁律: 复习面禁审视揭短词 ───────────────────────────
var FORBIDDEN = ["看穿", "识破", "揭穿", "露馅", "拆穿"];
var surfaces = [
  vmPath,
  path.join(__dirname, "../packageDeeptutor/pages/luban/review/review.js"),
  path.join(__dirname, "../packageDeeptutor/pages/luban/review/review.wxml"),
];
surfaces.forEach(function (file) {
  var text = fs.readFileSync(file, "utf8");
  FORBIDDEN.forEach(function (word) {
    assert.strictEqual(
      text.indexOf(word),
      -1,
      path.basename(file) + " 含禁词「" + word + "」(文案铁律: 帮你变强基调)",
    );
  });
});

// ── 5. 回归防线: review 页只消费 unified report 的 pack_review ──
var reviewJs = fs.readFileSync(surfaces[1], "utf8");
assert.strictEqual(
  reviewJs.indexOf("getLubanRetestItems"),
  -1,
  "review 页禁止逐站探测 retest-items 当到期语义(唯一权威=/luban/review-due)",
);
assert.strictEqual(reviewJs.indexOf("getLubanReviewDue"), -1, "review 页不得再拉第二份 learner-state 到期读模型");
assert.ok(reviewJs.indexOf("pack_review") >= 0, "review 页必须消费 unified learning report 的 pack_review");

console.log("test_review_view_model: all assertions passed");
