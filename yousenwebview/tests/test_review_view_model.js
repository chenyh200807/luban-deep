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
      { pack_id: "F16", title: "屋面防水", due_at: "2026-07-04T00:00:00+08:00", retest_available: true },
      { pack_id: "A01", title: "检验批", due_at: "2026-07-04T00:00:00+08:00", retest_available: false },
    ],
    learned_count: 2,
    authority: "revalidation_queue",
  },
  mistakeBook: { activeCount: 3, errorBars: [{ key: "E03", label: "关键词缺失", count: 2 }] },
});
assert.strictEqual(built.dueCount, 2);
assert.strictEqual(built.learnedCount, 2);
assert.strictEqual(built.duePercent, 100);
assert.strictEqual(built.mistakeActiveCount, 3);
assert.strictEqual(built.isEmpty, false);
assert.strictEqual(built.firstDue.packId, "F16");
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
assert.strictEqual(empty.isEmpty, true);
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
assert.strictEqual(flagOff.isEmpty, false, "有点亮站但旗标关→非空态,到期清单为空");
assert.strictEqual(flagOff.dueCount, 0);

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

// ── 5. 回归防线: review 页禁 N+1 retest-items 探测(到期收权服务端) ──
var reviewJs = fs.readFileSync(surfaces[1], "utf8");
assert.strictEqual(
  reviewJs.indexOf("getLubanRetestItems"),
  -1,
  "review 页禁止逐站探测 retest-items 当到期语义(唯一权威=/luban/review-due)",
);
assert.ok(
  reviewJs.indexOf("getLubanReviewDue") >= 0,
  "review 页必须消费服务端 review-due 投影",
);

console.log("test_review_view_model: all assertions passed");
