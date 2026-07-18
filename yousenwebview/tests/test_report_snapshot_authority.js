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
assert.ok(cache.SNAPSHOT_MAX_AGE_MS > 0, "snapshot ttl must exist");
assert.strictEqual(cache.FRESH_MAX_AGE_MS, undefined,
  "fresh-skip gate was refuted by adversarial review and must stay deleted");

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

// 时钟回拨:cachedAt 在未来 → 负年龄快照必须视为无效(否则永不过期,
// 且会把所有静默刷新永久压制——review 发现 #4)。
storage[envelopeKey].value.cachedAt = Date.now() + 10 * 60 * 1000;
assert.strictEqual(cache.readWithMeta("student_a", cache.SNAPSHOT_MAX_AGE_MS), null,
  "future-stamped snapshot (negative age) must not hydrate");
storage[envelopeKey].value.cachedAt = Date.now();

// --- writeIfFresher 写序守卫(双写者 ABA 防护) ---
var snapshotA2 = { report: { user_id: "student_a", overview: { focus_hint: "新" } } };
var beforeExisting = Date.now() - 60 * 1000; // 孤儿请求:发起早于现存快照写入
assert.strictEqual(cache.writeIfFresher("student_a", snapshotA2, beforeExisting), false,
  "orphan response fetched before the existing snapshot was written must not overwrite it");
assert.deepStrictEqual(cache.read("student_a", cache.SNAPSHOT_MAX_AGE_MS), snapshotA,
  "existing snapshot survives the orphan write attempt");
assert.strictEqual(cache.writeIfFresher("student_a", snapshotA2, Date.now()), true,
  "a fetch started after the existing write wins");
assert.deepStrictEqual(cache.read("student_a", cache.SNAPSHOT_MAX_AGE_MS), snapshotA2);
assert.strictEqual(cache.writeIfFresher("student_a", snapshotA, 0), true,
  "missing fetchStartedAt degrades to plain write");
cache.write("student_a", snapshotA);
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

// settle() 把失败源映成 {} —— builder 必须归一化为 null(review 发现 #3:
// 空对象入快照会让消费页把"缺失"当"有数据"渲染半残模块)。
var builtEmptySources = reportSnapshot.buildUnifiedReportSnapshot({
  report: validReport,
  homeDashboard: {},
  lessons: {},
});
assert.strictEqual(builtEmptySources.homeDashboard, null, "settled-to-{} dashboard normalizes to null");
assert.strictEqual(builtEmptySources.lessons, null, "settled-to-{} lessons normalizes to null");

// 学习页 live admission 必须验证三路业务体，而不是把 HTTP 200/空对象当真相。
var validDashboard = {
  learner_settings: {},
  review: {},
  mastery: {},
  today: {},
  next_step: {
    mode: "learn_next",
    source_authority: "home-next-step-projection",
    source_ref: "pack:c04",
    reason: "canonical next station",
  },
};
var validLessons = { pack_universe: 1, lessons: [{ pack_id: "c04" }] };
assert.strictEqual(reportSnapshot.isHomeDashboardPayload({}), false);
assert.strictEqual(reportSnapshot.isHomeDashboardPayload(validDashboard), true);
var validFallbackDashboard = JSON.parse(JSON.stringify(validDashboard));
validFallbackDashboard.next_step.mode = "learn_fallback";
validFallbackDashboard.next_step.source_authority = "pack_manifest.registry_order";
assert.strictEqual(reportSnapshot.isHomeDashboardPayload(validFallbackDashboard), true,
  "canonical all-learned fallback remains a valid live dashboard mode");
assert.strictEqual(reportSnapshot.isLubanLessonsPayload({ lessons: [] }), false,
  "missing pack_universe cannot enter the live projection");
assert.strictEqual(reportSnapshot.isLubanLessonsPayload(validLessons), true);
assert.strictEqual(reportSnapshot.isCompleteLearnSnapshot({
  report: validReport,
  homeDashboard: validDashboard,
  lessons: validLessons,
}), true);
assert.strictEqual(reportSnapshot.isCompleteLearnSnapshot({
  report: validReport,
  homeDashboard: {},
  lessons: validLessons,
}), false, "partial cached triples must not hydrate the actionable learning page");
var arrayReport = JSON.parse(JSON.stringify(validReport));
arrayReport.overview = [];
arrayReport.freshness = [];
arrayReport.learning_brain = [];
assert.strictEqual(reportSnapshot.isLearningReportPayload(arrayReport), false,
  "array-shaped nested fields must not enter live/cache as objects");
var stringSchemaReport = JSON.parse(JSON.stringify(validReport));
stringSchemaReport.schema_version = "2";
assert.strictEqual(reportSnapshot.isLearningReportPayload(stringSchemaReport), false,
  "schema identity is an integer contract, not a coercible string");

delete global.wx;
console.log("test_report_snapshot_authority: all assertions passed");
