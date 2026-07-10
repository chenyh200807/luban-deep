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
      { pack_id: "A01", title: "检验批验收程序", content_sha256: "sha_a01", summary: "四级验收层级" },
      { pack_id: "N01", title: "网络计划关键线路", content_sha256: "sha_n01", summary: "关键工作判定" },
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

// ── 副标题:后端 summary(概念卡 front)优先;无 summary 回退前端显示层 map;两者都无才空 ──
ok("poster subtitle: backend summary > frontend map > empty", () => {
  const vm = buildLearnViewModel(FULL);
  const a01 = vm.posters.find((p) => p.pack_id === "A01");
  assert.strictEqual(a01.subtitle, "四级验收层级"); // 后端 summary 透传
  const n01 = vm.posters.find((p) => p.pack_id === "N01");
  assert.strictEqual(n01.subtitle, "关键工作判定");
  const s05 = vm.posters.find((p) => p.pack_id === "S05");
  assert.strictEqual(s05.subtitle, "临时用电三大系统"); // 无 summary → 回退前端 map
  // 既无 summary 又不在 map 的站 → 真留空(不造词)
  const vm2 = buildLearnViewModel({ homeDashboard: {}, report: {},
    lessons: { lessons: [{ pack_id: "Z99", title: "未登记站", content_sha256: "z" }] } });
  const z99 = vm2.posters.find((p) => p.pack_id === "Z99");
  assert.strictEqual(z99.subtitle, "");
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

// ── practice_active → 今日主任务卡 = 2 分钟 MCQ 轻练(PRD v1.3 §0.0 头牌收口) ──
ok("practice_active arm → today task is MCQ light practice (not case grading)", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "N01", reason: "练:你漏的采分点" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.ok(vm.todayTask);
  assert.strictEqual(vm.todayTask.cta, "开始 2 分钟轻练");
  assert.strictEqual(vm.todayTask.task_type, "light_practice");
  assert.strictEqual(vm.todayTask.estimated_minutes, 2);
  assert.strictEqual(vm.todayTask.mode, "topic"); // 路由到 assessment 专题模式
  assert.strictEqual(vm.todayTask.pack_id, "N01"); // 带上推荐考点
  assert.strictEqual(vm.todayTask.concept, "网络计划关键线路");
  assert.ok(vm.todayTask.title.indexOf("网络计划关键线路") === 0);
  assert.strictEqual(vm.todayTask.reason, "练:你漏的采分点");
  // 案例题批改已降级:今日任务不再携带案例批改 prompt(不走 chat 判分流)
  assert.strictEqual(vm.todayTask.prompt, undefined);
});

// ── 兜底臂(有站可学但非 practice_active)→ 同样是 MCQ 轻练,带该站考点 ──
ok("fallback arm → MCQ light practice carries next-station pack/concept", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "learn_next", source_ref: "N01", reason: "下一站" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.ok(vm.todayTask);
  assert.strictEqual(vm.todayTask.task_type, "light_practice");
  assert.strictEqual(vm.todayTask.mode, "topic");
  assert.strictEqual(vm.todayTask.pack_id, "N01");
  assert.strictEqual(vm.todayTask.prompt, undefined);
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

// ── 海报竖排书法名:>6 字截断为单列显示名(live 绿灯站 26/28 标题超长),
//    title 保留全名(下一站卡/详情消费) ──
ok("poster name uses registered 简称; title keeps full text; unregistered falls back to clamp", () => {
  const vm = buildLearnViewModel({
    homeDashboard: {},
    report: {},
    lessons: { lessons: [
      { pack_id: "F02", title: "卷材防水施工顺序与搭接方向", content_sha256: "s1" },
      { pack_id: "F05", title: "渗漏治理诊断", content_sha256: "s2" },
      { pack_id: "Z99", title: "未登记简称的长站点标题", content_sha256: "s3" },
    ] },
  });
  const f02 = vm.posters.find((p) => p.pack_id === "F02");
  assert.strictEqual(f02.name, "卷材防水");        // 简称(显示层),非旧 6 字截断
  assert.strictEqual(f02.title, "卷材防水施工顺序与搭接方向"); // 全名不变(详情页/下一站卡用)
  const f05 = vm.posters.find((p) => p.pack_id === "F05");
  assert.strictEqual(f05.name, "渗漏治理");        // 简称
  const z99 = vm.posters.find((p) => p.pack_id === "Z99");
  assert.strictEqual(z99.name, "未登记简称的"); // 未登记 → 回退旧 6 字截断止血
  assert.strictEqual(z99.title, "未登记简称的长站点标题");
});

console.log("\nlearn-view-model: " + passed + " passed");
