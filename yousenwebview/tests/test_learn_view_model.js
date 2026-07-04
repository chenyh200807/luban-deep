// node contract 测试:learn-view-model 纯函数
// 断言:齐全/字段缺/全空三态 → setData 形状正确 + 降级不抛 + fallback 非空(day-0 不白屏)
// 运行: node yousenwebview/tests/test_learn_view_model.js

const assert = require("assert");
const { buildLearnViewModel, PACK_UNIVERSE } = require("../packageDeeptutor/utils/learn-view-model");

let passed = 0;
function ok(name, fn) {
  fn();
  passed += 1;
  console.log("  ✓ " + name);
}

// ── 全空(= test2 后端未部署常态):必须不抛 + 合理空态 ──
ok("empty inputs degrade without throw", () => {
  const vm = buildLearnViewModel({});
  assert.strictEqual(vm.nextStation, null);
  assert.deepStrictEqual(vm.posters, []);
  assert.strictEqual(vm.dueCount, 0);
  assert.strictEqual(vm.todayTask, null);
  assert.strictEqual(vm.litCount, 0);
  assert.strictEqual(vm.packUniverse, PACK_UNIVERSE);
  assert.strictEqual(vm.hasSupply, false);
});

ok("null/garbage inputs degrade without throw", () => {
  const vm = buildLearnViewModel({ homeDashboard: null, report: "x", lessons: 42 });
  assert.strictEqual(vm.hasSupply, false);
  assert.deepStrictEqual(vm.posters, []);
});

// ── 齐全:下一站/路线/海报/复习/指标全部映射 ──
const FULL = {
  homeDashboard: {
    next_step: {
      mode: "learn_next",
      source_authority: "pack_lifecycle_projection",
      source_ref: "N01",
      reason: "下一站:网络计划关键线路",
    },
  },
  lessons: {
    lessons: [
      { pack_id: "A01", title: "检验批验收程序", content_sha256: "sha_a01" },
      { pack_id: "N01", title: "网络计划关键线路", content_sha256: "sha_n01" },
      { pack_id: "S05", title: "临时用电三级配电", content_sha256: "sha_s05" },
    ],
  },
  report: {
    pack_lifecycle: {
      state_machine: ["unlearned", "exposed", "practiced", "mastered", "dormant"],
      packs: {
        A01: { lifecycle_state: "mastered" },
        N01: { lifecycle_state: "unlearned" },
        S05: { lifecycle_state: "practiced" },
      },
    },
    revalidation_queue: { items: [{ probe_id: "p1" }, { probe_id: "p2" }] },
    overview: { recent_three_done: 8, weak_point_count: 3 },
    mastery: { overall_mastery: { score: 72 } },
  },
};

ok("full data maps next station with reason and title", () => {
  const vm = buildLearnViewModel(FULL);
  assert.strictEqual(vm.nextStation.pack_id, "N01");
  assert.strictEqual(vm.nextStation.title, "网络计划关键线路");
  assert.strictEqual(vm.nextStation.reason, "下一站:网络计划关键线路");
  assert.strictEqual(vm.nextStation.card_sha, "sha_n01");
  assert.strictEqual(vm.nextStation.green, true);
});

ok("lit count = practiced+mastered+dormant, universe=40", () => {
  const vm = buildLearnViewModel(FULL);
  assert.strictEqual(vm.litCount, 2); // A01 mastered + S05 practiced
  assert.strictEqual(vm.packUniverse, 40);
});

ok("posters: recommended first(red), then ink lit, no dup", () => {
  const vm = buildLearnViewModel(FULL);
  assert.strictEqual(vm.posters[0].pack_id, "N01");
  assert.strictEqual(vm.posters[0].state, "red"); // recommended
  assert.strictEqual(vm.posters[0].recommended, true);
  const a01 = vm.posters.find((p) => p.pack_id === "A01");
  assert.strictEqual(a01.state, "ink"); // mastered
  const ids = vm.posters.map((p) => p.pack_id);
  assert.strictEqual(new Set(ids).size, ids.length, "no duplicate posters");
});

ok("due count + stats mapped", () => {
  const vm = buildLearnViewModel(FULL);
  assert.strictEqual(vm.dueCount, 2);
  assert.strictEqual(vm.stats.recent_practice, 8);
  assert.strictEqual(vm.stats.pending_errors, 3);
  assert.strictEqual(vm.stats.mastery_trend, 72);
  assert.strictEqual(vm.hasSupply, true);
});

// ── H3:非绿灯 pack(不在 lessons)一律"即将开通"+锁,不硬编码真站 ──
ok("H3: non-green pack shows 即将开通 + locked, never fabricated", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "learn_next", source_ref: "Z99", reason: "x" } },
    report: { pack_lifecycle: { packs: { Z99: { lifecycle_state: "unlearned" } } } },
    lessons: { lessons: [] }, // 无绿灯
  });
  assert.strictEqual(vm.nextStation.title, "即将开通");
  assert.strictEqual(vm.nextStation.green, false);
  const z = vm.posters.find((p) => p.pack_id === "Z99");
  assert.strictEqual(z.locked, true);
  assert.strictEqual(z.title, "即将开通");
});

// ── next_step=unavailable 但有绿灯站 → day-0 兜底到首个绿灯站(舞台始终显示) ──
ok("unavailable but green lessons → day-0 fallback station renders stage", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "unavailable", source_ref: "", reason: "" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.ok(vm.nextStation, "fallback station must render the stage");
  assert.strictEqual(vm.nextStation.mode, "learn_fallback");
  assert.strictEqual(vm.nextStation.green, true);
  assert.ok(vm.todayTask, "today task card must also render");
});

// ── practice_active → 今日任务卡出现 ──
ok("practice_active arm → today task card", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "N01", reason: "练:你漏的采分点" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.ok(vm.todayTask);
  assert.strictEqual(vm.todayTask.cta, "开始半写训练");
  assert.ok(vm.todayTask.title.indexOf("网络计划关键线路") === 0);
});


// ── 增强:无 lifecycle 时并入绿灯 lessons(test2 常态,route map 不空) ──
ok("green lessons appear as posters even without lifecycle", () => {
  const vm = buildLearnViewModel({
    homeDashboard: {},
    report: {}, // 无 pack_lifecycle
    lessons: { lessons: [
      { pack_id: "A01", title: "检验批验收程序", content_sha256: "s1" },
      { pack_id: "N01", title: "网络计划关键线路", content_sha256: "s2" },
    ] },
  });
  assert.strictEqual(vm.posters.length, 2);
  assert.ok(vm.posters.every((p) => p.green === true));
  // day-0 兜底:首站=推荐(朱红),其余未学(纸)
  assert.strictEqual(vm.posters[0].state, "red");
  assert.strictEqual(vm.posters[0].recommended, true);
  assert.ok(vm.posters.slice(1).every((p) => p.state === "paper"));
  assert.strictEqual(vm.hasSupply, true);
});

console.log("\nlearn-view-model: " + passed + " passed");
