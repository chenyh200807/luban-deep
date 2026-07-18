// Run: node yousenwebview/tests/test_report_snapshot_authority.js
// 守两件事:1) report-cache readWithMeta 的年龄语义与 read 一致;
// 2) report-snapshot builder 是快照组装唯一权威(有效 report → v2 形状,无效 → null)。
var assert = require("assert");
var path = require("path");

var storage = {};
global.wx = {
  getStorageSync: function (key) { return storage[key]; },
  setStorageSync: function (key, value) { storage[key] = value; },
  removeStorageSync: function (key) { delete storage[key]; },
};

var cachePath = path.join(__dirname, "../packageDeeptutor/utils/report-cache.js");
delete require.cache[require.resolve(cachePath)];
var cache = require(cachePath);

var builderPath = path.join(
  __dirname,
  "../packageDeeptutor/utils/report-snapshot.js",
);
delete require.cache[require.resolve(builderPath)];
var reportSnapshot = require(builderPath);

// --- readWithMeta 语义 ---
assert.strictEqual(typeof cache.readWithMeta, "function");
assert.ok(cache.FRESH_MAX_AGE_MS > 0 && cache.FRESH_MAX_AGE_MS < cache.SNAPSHOT_MAX_AGE_MS,
  "fresh window must be shorter than snapshot ttl");

var snapshotA = { report: { user_id: "student_a", overview: {} } };
assert.strictEqual(cache.write("student_a", snapshotA), true);
var hit = cache.readWithMeta("student_a", cache.SNAPSHOT_MAX_AGE_MS);
assert.ok(hit && hit.snapshot, "fresh write must be readable with meta");
assert.deepStrictEqual(hit.snapshot, snapshotA);
assert.ok(typeof hit.ageMs === "number" && hit.ageMs >= 0 && hit.ageMs < 5000,
  "ageMs must reflect just-written snapshot");
assert.strictEqual(cache.readWithMeta("student_b", cache.SNAPSHOT_MAX_AGE_MS), null,
  "owner isolation holds for readWithMeta");
// 过期语义与原 read 一致(严格大于):回拨 cachedAt 模拟 2 分钟前的快照。
var envelopeKey = cache.keyFor("student_a");
storage[envelopeKey].value.cachedAt = Date.now() - 2 * 60 * 1000;
assert.strictEqual(cache.readWithMeta("student_a", 60 * 1000), null,
  "snapshot older than maxAge must not hydrate");
var staleHit = cache.readWithMeta("student_a", cache.SNAPSHOT_MAX_AGE_MS);
assert.ok(staleHit && staleHit.ageMs >= 2 * 60 * 1000 - 50,
  "ageMs must reflect the backdated write");
assert.ok(staleHit.ageMs > cache.FRESH_MAX_AGE_MS,
  "a 2min-old snapshot is hydratable but not fresh — the SWR discriminator");
storage[envelopeKey].value.cachedAt = Date.now();
assert.deepStrictEqual(cache.read("student_a", cache.SNAPSHOT_MAX_AGE_MS), snapshotA,
  "read stays a thin view over readWithMeta");

// --- builder 权威 ---
var validReport = {
  schema_version: 2,
  authority: { read_model: "learning-report-read-model" },
  overview: {
    today_done: 3,
    daily_target: 5,
    streak_days: 2,
    due_today_count: 4,
    weak_node_count: 1,
    focus_hint: "先补基坑支护",
    learner_level: "L2",
    study_tip: "错因优先",
  },
  freshness: {},
  learning_brain: {
    weak_points: [
      { display_title: "基坑支护选型", claim: "", concept_id: "c1" },
      { claim: "隐蔽验收程序", concept_id: "c2" },
    ],
  },
  mastery: { packs: [] },
  radar_dimensions: [{ name: "施工技术", value: 0.62 }],
  degraded_sources: ["home_dashboard", "home_dashboard"],
  source_status: { learning_report: "ok" },
  learner_facing: { tone: "warm" },
};

var built = reportSnapshot.buildUnifiedReportSnapshot({
  report: validReport,
  homeDashboard: { next_step: {} },
  lessons: { items: [] },
});
assert.ok(built, "valid learning report must build a snapshot");
assert.strictEqual(built.report, validReport);
assert.deepStrictEqual(built.homeDashboard, { next_step: {} });
assert.deepStrictEqual(built.lessons, { items: [] });
assert.deepStrictEqual(built.progress, { today_done: 3, daily_target: 5, streak_days: 2 });
assert.strictEqual(built.home.review.due_today, 4);
assert.strictEqual(built.home.mastery.weak_nodes.length, 1, "weak_node_count caps the slice");
assert.strictEqual(built.home.mastery.weak_nodes[0].name, "基坑支护选型");
assert.strictEqual(built.assessment.level, "L2");
assert.deepStrictEqual(built.degradedSources, ["home_dashboard"], "degraded sources are deduped");
assert.strictEqual(built.degraded, true);
assert.strictEqual(built.learningBrain, validReport.learning_brain);

// 无效 report(空对象/缺 authority)→ null,写者据此跳过 cache.write,防污染。
assert.strictEqual(reportSnapshot.buildUnifiedReportSnapshot({ report: {} }), null);
assert.strictEqual(reportSnapshot.buildUnifiedReportSnapshot({}), null);
assert.strictEqual(
  reportSnapshot.buildUnifiedReportSnapshot({ report: null, homeDashboard: {}, lessons: {} }),
  null,
);

// freshness.window_truncated 追加 learning_report_window 降级源。
var truncated = JSON.parse(JSON.stringify(validReport));
truncated.freshness = { window_truncated: true };
truncated.degraded_sources = [];
var builtTruncated = reportSnapshot.buildUnifiedReportSnapshot({ report: truncated });
assert.deepStrictEqual(builtTruncated.degradedSources, ["learning_report_window"]);
assert.strictEqual(builtTruncated.degraded, true);
assert.strictEqual(builtTruncated.homeDashboard, null, "missing dashboard degrades to null, not {}");

delete global.wx;
console.log("test_report_snapshot_authority: all assertions passed");
