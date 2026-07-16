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
  assert.strictEqual(vm.dueCount, undefined);
  assert.strictEqual(vm.todayTask, null);
  assert.strictEqual(vm.reviewCard, null);
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
    learner_settings: { exam_date: "2026-09-19", daily_target: 10 },
    next_step: {
      mode: "learn_next",
      source_authority: "pack_lifecycle_projection",
      source_ref: "N01",
      reason: "下一站:网络计划关键线路",
    },
  },
  lessons: {
    pack_universe: 41,
    lessons: [
      { pack_id: "A01", title: "检验批验收程序", content_sha256: "sha_a01", card_hosted: true, summary: "四级验收层级" },
      { pack_id: "N01", title: "网络计划关键线路", content_sha256: "sha_n01", card_hosted: true, summary: "关键工作判定", retest_available: true, light_practice_available: true },
      { pack_id: "S05", title: "临时用电三级配电", content_sha256: "sha_s05", card_hosted: true },
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
    revalidation_queue: { items: [] },
    pack_review: {
      authority: "revalidation_queue",
      enabled: true,
      due: [],
    },
    overview: { recent_three_done: 8, weak_point_count: 3, today_done: 4, daily_target: 10 },
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
  assert.strictEqual(vm.nextStation.card_hosted, true);
});

ok("lit count = practiced+mastered+dormant, universe comes from manifest API", () => {
  const vm = buildLearnViewModel(FULL);
  assert.strictEqual(vm.litCount, 2); // A01 mastered + S05 practiced
  assert.strictEqual(vm.packUniverse, 41);
});

ok("old lessons payload without pack_universe keeps compatibility fallback", () => {
  const vm = buildLearnViewModel({ homeDashboard: {}, report: {}, lessons: { lessons: [] } });
  assert.strictEqual(vm.packUniverse, PACK_UNIVERSE);
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

ok("activity stats map without exposing a frontend mastery decision", () => {
  const vm = buildLearnViewModel(FULL);
  assert.strictEqual(vm.dueCount, undefined);
  assert.strictEqual(vm.stats.recent_practice, 8);
  assert.strictEqual(vm.stats.pending_errors, 3);
  assert.strictEqual(vm.stats.mastery_score, undefined);
  assert.strictEqual(vm.examDate, "2026-09-19");
  assert.deepStrictEqual(vm.todayProgress, { done: 4, target: 10, percent: 40 });
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
  assert.strictEqual(
    vm.todayTask,
    null,
    "browse fallback may keep the stage alive but must not compete with server next_step as today's task",
  );
});

ok("day-0 fallback prefers a green station with a hosted microlesson", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "unavailable" } },
    report: {},
    lessons: { lessons: [
      { pack_id: "B02", title: "基坑", content_sha256: "b", card_hosted: false },
      { pack_id: "C02", title: "质量", content_sha256: "c", card_hosted: true },
    ] },
  });
  assert.strictEqual(vm.nextStation.pack_id, "C02");
  assert.strictEqual(vm.nextStation.card_hosted, true);
});

ok("unhosted personalized next step falls back to a playable recommended microlesson", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "learn_next", source_ref: "B02", reason: "x" } },
    report: {},
    lessons: { lessons: [
      { pack_id: "B02", title: "基坑", content_sha256: "b", card_hosted: false },
      { pack_id: "C02", title: "质量", content_sha256: "c", card_hosted: true },
    ] },
  });
  assert.strictEqual(vm.nextStation.pack_id, "C02");
  assert.strictEqual(vm.nextStation.green, true);
  assert.strictEqual(vm.nextStation.card_hosted, true);
  assert.strictEqual(vm.nextStation.mode, "hosted_fallback");
  assert.strictEqual(vm.nextStation.evidenceBacked, false);
  const b02 = vm.posters.find((p) => p.pack_id === "B02");
  assert.strictEqual(b02.card_hosted, false);
  assert.strictEqual(b02.recommended, false);
});

ok("when no hosted microlesson exists the route stays honest and the stage remains blocked", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "learn_next", source_ref: "B02", reason: "x" } },
    report: {},
    lessons: { lessons: [{ pack_id: "B02", title: "基坑", content_sha256: "b", card_hosted: false }] },
  });
  assert.strictEqual(vm.nextStation.pack_id, "B02");
  assert.strictEqual(vm.nextStation.green, true);
  assert.strictEqual(vm.nextStation.card_hosted, false);
  assert.strictEqual(vm.nextStation.title, "基坑");
});

ok("legacy lessons without card_hosted keep the station navigable for detail authority", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "learn_next", source_ref: "A01", reason: "x" } },
    report: {},
    lessons: { lessons: [{ pack_id: "A01", title: "检验批验收程序", content_sha256: "a" }] },
  });
  assert.strictEqual(vm.nextStation.pack_id, "A01");
  assert.strictEqual(vm.nextStation.green, true);
  assert.strictEqual(vm.nextStation.card_hosted, null);
  const a01 = vm.posters.find((p) => p.pack_id === "A01");
  assert.strictEqual(a01.card_hosted, null);
});

// ── practice_active → 今日主任务卡 = 2 分钟 MCQ 轻练(PRD v1.3 §0.0 头牌收口) ──
ok("practice_active arm → today task is MCQ light practice (not case grading)", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_n01", target_pack_id: "N01", reason: "练:你漏的采分点" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.ok(vm.todayTask);
  assert.strictEqual(vm.todayTask.cta, "完成刚学内容的 5 题检验");
  // N01 fixture 有 signed 变体池 → practice_kind 按供给真值路由到 retest forward
  assert.strictEqual(vm.todayTask.practice_kind, "retest");
  assert.strictEqual(vm.todayTask.supplyNote, "");
  assert.strictEqual(vm.todayTask.task_type, "light_practice");
  assert.strictEqual(vm.todayTask.task_state, "practice_active");
  assert.strictEqual(vm.todayTask.action_kind, "retest");
  assert.strictEqual(vm.todayTask.estimated_minutes, 2);
  assert.strictEqual(vm.todayTask.mode, "forward");
  assert.strictEqual(vm.todayTask.pack_id, "N01"); // 带上推荐考点
  assert.strictEqual(vm.todayTask.training_intent_id, "ti_n01");
  assert.strictEqual(vm.todayTask.concept, "网络计划关键线路");
  assert.ok(vm.todayTask.title.indexOf("网络计划关键线路") === 0);
  assert.strictEqual(vm.todayTask.reason, "练:你漏的采分点");
  assert.strictEqual(vm.todayTask.ctaLabel, "开始训练");
  assert.strictEqual(vm.todayTask.light_practice_available, true);
  assert.strictEqual(vm.todayTask.secondaryCta, undefined);
  // 案例题批改已降级:今日任务不再携带案例批改 prompt(不走 chat 判分流)
  assert.strictEqual(vm.todayTask.prompt, undefined);
});

ok("practice source_ref is intent identity, never treated as a pack id", () => {
  const vm = buildLearnViewModel({
    homeDashboard: {
      next_step: {
        mode: "practice_active",
        source_ref: "lti_not_a_pack",
        target_pack_id: "F16",
        reason: "继续练",
      },
    },
    report: FULL.report,
    lessons: {
      lessons: [
        { pack_id: "F16", title: "屋面防水起鼓割补", content_sha256: "sha_f16", retest_available: true, light_practice_available: true },
      ],
    },
  });
  assert.strictEqual(vm.nextStation.pack_id, "F16");
  assert.strictEqual(vm.nextStation.green, true);
  assert.strictEqual(vm.todayTask.training_intent_id, "lti_not_a_pack");
});

ok("signed variant supply does not expose forward CTA while rollout is off", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_f16", target_pack_id: "F16" } },
    report: FULL.report,
    lessons: {
      lessons: [
        { pack_id: "F16", title: "屋面防水起鼓割补", retest_available: true, light_practice_available: false },
      ],
    },
  });
  assert.strictEqual(vm.todayTask.practice_kind, "none");
  assert.strictEqual(vm.todayTask.cta, "");
});

ok("server review_due next step supplies the due probe and target station", () => {
  const vm = buildLearnViewModel({
    homeDashboard: {
      next_step: {
        mode: "review_due",
        source_ref: "rvp_f16",
        target_pack_id: "F16",
        reason: "到期复验",
      },
    },
    report: {
      ...FULL.report,
      // review 资格消费 canonical due 条目(A5):供给真值在 pack_review,不在 lessons 旗标
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        due: [{ pack_id: "F16", title: "屋面防水起鼓割补", probe_id: "rvp_f16", retest_available: true }],
      },
    },
    lessons: {
      lessons: [
        { pack_id: "F16", title: "屋面防水起鼓割补", content_sha256: "sha_f16", retest_available: true, light_practice_available: true },
      ],
    },
  });
  assert.strictEqual(vm.nextStation.pack_id, "F16");
  assert.strictEqual(vm.todayTask.probe_id, "rvp_f16");
  assert.strictEqual(vm.todayTask.training_intent_id, "");
  assert.strictEqual(vm.todayTask.task_state, "review_due");
  assert.strictEqual(vm.todayTask.action_kind, "retest");
  assert.strictEqual(vm.todayTask.mode, "review");
  // 周期由服务端 due 裁决,前端不得声称"昨天"(可能是 3 日/稳定周期抽查)
  assert.strictEqual(vm.todayTask.cta, "用 2 分钟完成到期验证");
});

ok("frontend never creates a competing priority from pack_review", () => {
  const vm = buildLearnViewModel({
    homeDashboard: {
      next_step: {
        mode: "practice_active",
        source_ref: "intent_n01",
        target_pack_id: "N01",
        reason: "普通课后练",
      },
    },
    report: {
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        due: [{ pack_id: "S05", title: "临时用电", probe_id: "probe_s05" }],
      },
    },
    lessons: {
      lessons: [
        { pack_id: "N01", title: "网络计划", light_practice_available: true },
        { pack_id: "S05", title: "临时用电", light_practice_available: true },
      ],
    },
  });
  assert.strictEqual(vm.todayTask.pack_id, "N01");
  assert.strictEqual(vm.todayTask.training_intent_id, "intent_n01");
  assert.strictEqual(vm.todayTask.task_state, "practice_active");
  assert.strictEqual(vm.todayTask.cta, "完成刚学内容的 5 题检验");
});

// ── 兜底臂(无到期/未闭合练习)→ 推荐微课成为唯一主任务 ──
ok("fallback arm → recommended microlesson becomes the primary task", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "learn_next", source_ref: "N01", reason: "下一站" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.ok(vm.todayTask);
  assert.strictEqual(vm.todayTask.task_type, "microlesson");
  assert.strictEqual(vm.todayTask.task_state, "learn_next");
  assert.strictEqual(vm.todayTask.action_kind, "lesson");
  assert.strictEqual(vm.todayTask.mode, "learn");
  assert.strictEqual(vm.todayTask.pack_id, "N01");
  assert.strictEqual(vm.todayTask.cta, "学这一小节，随后做 5 题");
  assert.strictEqual(vm.todayTask.prompt, undefined);
});

// ── 一等任务只走通用 retest 供给；Pack 专属看穿 spike 不再参与学习首页 ──
ok("practice task ignores the legacy seethrough library and uses generic retest supply", () => {
  const vmA = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_n01", target_pack_id: "N01", reason: "r" } },
    report: FULL.report,
    lessons: FULL.lessons,
    seethroughLibrary: { total: 1, packs: [{ pack_id: "N01", title: "网络计划关键线路" }] },
  });
  assert.strictEqual(vmA.todayTask.practice_kind, "retest");
  // 无通用供给 → none: 主按钮不渲染(cta 空) + 诚实降级说明
  const vmC = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_a01", target_pack_id: "A01", reason: "r" } },
    report: FULL.report,
    lessons: FULL.lessons, // A01 无 retest_available 字段 = 保守 false
  });
  assert.strictEqual(vmC.todayTask.practice_kind, "none");
  assert.strictEqual(vmC.todayTask.cta, "");
  assert.ok(vmC.todayTask.supplyNote.length > 0);
  // 看穿库响应畸形也不能影响通用路由
  const vmD = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_n01", target_pack_id: "N01", reason: "r" } },
    report: FULL.report,
    lessons: FULL.lessons,
    seethroughLibrary: "garbage",
  });
  assert.strictEqual(vmD.todayTask.practice_kind, "retest");
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
  assert.deepStrictEqual(vm.routePreview, vm.posters.slice(0, 3));
  assert.strictEqual(vm.nextStation.evidenceBacked, false);
  assert.strictEqual(vm.hasSupply, true);
});

ok("route preview never overwrites canonical lifecycle state for visual variety", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "learn_next", source_ref: "N01", reason: "起步" } },
    report: {
      pack_lifecycle: {
        packs: {
          N01: { lifecycle_state: "unlearned" },
          A01: { lifecycle_state: "practiced" },
          S05: { lifecycle_state: "unlearned" },
        },
      },
    },
    lessons: FULL.lessons,
  });
  const previewById = Object.fromEntries(vm.routePreview.map((item) => [item.pack_id, item]));
  assert.strictEqual(previewById.N01.state, "red");
  assert.strictEqual(previewById.A01.state, "ink");
  assert.strictEqual(previewById.S05.state, "paper");
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

// ══════════════════════════════════════════════════════════════
// 10a改 · 今日任务卡三层 + 旅程轨道 + 复习卡(单一权威红线)
// ══════════════════════════════════════════════════════════════

// ── 旅程轨道(红队 A1 收口):前端没有逐步完成证据 → 轨道=流程说明。
//    禁 done/勾;current 只由 next_step.mode 派生(CTA 对应步,唯一诚实声称);
//    第 5/6 步不承诺具体日程(复习周期由服务端 due 裁决,前端不写死"明日/3日")。 ──
const JOURNEY_LABELS = ["动画讲懂", "训练 5 题", "错因讲评", "轻练确认", "到期验证", "后续抽查"];

ok("journey: steps are exactly the 6 canonical labels; no schedule promises in copy", () => {
  const vm = buildLearnViewModel(FULL); // learn_next
  const j = vm.todayTask.journey;
  assert.ok(j, "todayTask must carry a journey");
  assert.deepStrictEqual(j.steps.map((s) => s.label), JOURNEY_LABELS);
  assert.strictEqual(j.total, 6);
  j.steps.forEach((s) => {
    assert.ok(s.label.indexOf("半写") === -1 && s.label.indexOf("填空") === -1);
    assert.ok(s.label.indexOf("明日") === -1 && s.label.indexOf("3 日") === -1,
      "journey copy must not hardcode a review schedule the server did not sign: " + s.label);
  });
});

ok("journey never claims done in any arm (frontend has no completion evidence)", () => {
  const arms = [
    { next_step: { mode: "learn_next", source_ref: "N01", reason: "r" } },
    { next_step: { mode: "practice_active", source_ref: "ti_n01", target_pack_id: "N01", reason: "r" } },
    { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01", reason: "r" } },
  ];
  arms.forEach((homeDashboard) => {
    const vm = buildLearnViewModel({ homeDashboard, report: FULL.report, lessons: FULL.lessons });
    const j = vm.todayTask.journey;
    assert.strictEqual(j.steps.filter((s) => s.state === "done").length, 0,
      "next_step.mode is a prescription, never completion evidence (" + homeDashboard.next_step.mode + ")");
  });
});

ok("journey learn_next → current step 1, tail two steps promised", () => {
  const vm = buildLearnViewModel(FULL);
  const j = vm.todayTask.journey;
  assert.strictEqual(j.currentIndex, 1);
  assert.strictEqual(j.steps[0].state, "current");
  assert.strictEqual(j.steps[1].state, "future");
  assert.strictEqual(j.steps[2].state, "future");
  assert.strictEqual(j.steps[3].state, "future");
  assert.strictEqual(j.steps[4].state, "promise"); // 到期验证=竹青虚环承诺
  assert.strictEqual(j.steps[5].state, "promise"); // 后续抽查=竹青虚环承诺
});

ok("journey practice_active → current step 2; earlier steps stay hollow, not done", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_n01", target_pack_id: "N01", reason: "r" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  const j = vm.todayTask.journey;
  assert.strictEqual(j.currentIndex, 2);
  // practice_active 只证明存在未 verified 的 training_intent,不证明动画讲懂已完成
  assert.strictEqual(j.steps[0].state, "future");
  assert.strictEqual(j.steps[1].state, "current");
  assert.strictEqual(j.steps[2].state, "future");
  assert.strictEqual(j.steps[3].state, "future");
  assert.strictEqual(j.steps[4].state, "promise");
  assert.strictEqual(j.steps[5].state, "promise");
});

ok("journey review_due → current=到期验证(step 5); nothing marked done, no line over hollow steps", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01", reason: "到期" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  const j = vm.todayTask.journey;
  assert.strictEqual(j.currentIndex, 5);
  assert.strictEqual(j.steps[0].state, "future");
  assert.strictEqual(j.steps[1].state, "future");
  assert.strictEqual(j.steps[2].state, "future");
  assert.strictEqual(j.steps[3].state, "future");
  assert.strictEqual(j.steps[4].state, "current"); // 到期验证=当前,不再是虚环
  assert.strictEqual(j.steps[5].state, "promise");
});

ok("journey draws no completion line: progressRatio/lineFillPercent removed", () => {
  ["learn_next", "practice_active", "review_due"].forEach((mode) => {
    const vm = buildLearnViewModel({
      homeDashboard: { next_step: { mode, source_ref: mode === "learn_next" ? "N01" : "ref", target_pack_id: "N01" } },
      report: FULL.report,
      lessons: FULL.lessons,
    });
    const j = vm.todayTask.journey;
    assert.strictEqual(j.progressRatio, undefined, "no progress ratio without completion evidence");
    assert.strictEqual(j.lineFillPercent, undefined, "progress line must never cross unverified steps");
  });
});

ok("journey exposes no mastery percent, only step-position facts", () => {
  const vm = buildLearnViewModel(FULL);
  const j = vm.todayTask.journey;
  assert.strictEqual(j.masteryPercent, undefined);
  assert.ok(j.currentIndex >= 1 && j.currentIndex <= 6);
  assert.ok(typeof j.ringPercent === "number" && j.ringPercent >= 0 && j.ringPercent <= 100);
});

// ── 轻练旁按钮(红队 A2 收口):到期验证优先,review_due 下不给绕开路径 ──
ok("review_due with supply must NOT expose light practice (no bypass around due verification)", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: FULL.report,
    lessons: FULL.lessons, // N01 供给真值为 true,但到期验证优先
  });
  assert.strictEqual(vm.todayTask.light_practice_available, false);
  assert.strictEqual(vm.todayTask.light_practice_visible, false);
});

ok("light practice stays usable only in learn/forward contexts", () => {
  const practice = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_n01", target_pack_id: "N01" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.strictEqual(practice.todayTask.light_practice_available, true);
  assert.strictEqual(practice.todayTask.light_practice_visible, true);
  const lesson = buildLearnViewModel(FULL); // learn_next
  assert.strictEqual(lesson.todayTask.light_practice_available, true);
  assert.strictEqual(lesson.todayTask.light_practice_visible, true);
});

// ── 主按钮短文案随任务类型;无供给时不给按钮(禁 dead click) ──
ok("ctaLabel: 开始验证 / 开始训练 / 继续学习 by task type; empty when no supply", () => {
  const review = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        due: [{ pack_id: "N01", title: "网络计划关键线路", probe_id: "rvp_n01", retest_available: true }],
      },
    },
    lessons: FULL.lessons,
  });
  assert.strictEqual(review.todayTask.ctaLabel, "开始验证");
  const lesson = buildLearnViewModel(FULL);
  assert.strictEqual(lesson.todayTask.ctaLabel, "继续学习");
  assert.strictEqual(lesson.todayTask.light_practice_available, true); // N01 供给已接通
  // 无 retest 供给的 practice_active → ctaLabel 空(按钮隐藏)+ 诚实降级说明
  const none = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_a01", target_pack_id: "A01" } },
    report: FULL.report,
    lessons: FULL.lessons, // A01 无 light_practice_available
  });
  assert.strictEqual(none.todayTask.ctaLabel, "");
  assert.strictEqual(none.todayTask.light_practice_available, false);
  assert.ok(none.todayTask.supplyNote.length > 0);
});

ok("practice title claims 5 题 only when the retest pool is really available", () => {
  const withSupply = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_n01", target_pack_id: "N01" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.ok(withSupply.todayTask.title.indexOf("训练 5 题") >= 0);
  const noSupply = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_a01", target_pack_id: "A01" } },
    report: FULL.report,
    lessons: FULL.lessons,
  });
  assert.strictEqual(noSupply.todayTask.title.indexOf("训练 5 题"), -1);
});

// ── 复习卡:只是到期状态视图,单一权威=next_step;禁第二任务源 ──
const DUE_REPORT = {
  ...FULL.report,
  pack_review: {
    authority: "revalidation_queue",
    enabled: true,
    due: [
      { pack_id: "N01", title: "网络计划关键线路", probe_id: "rvp_n01", retest_available: true },
      { pack_id: "S05", title: "临时用电三级配电", probe_id: "rvp_s05", retest_available: true },
    ],
    learned_count: 3,
  },
};

ok("review card renders only when next_step already adjudicated review_due", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01", reason: "到期" } },
    report: DUE_REPORT,
    lessons: FULL.lessons,
  });
  assert.ok(vm.reviewCard);
  assert.strictEqual(vm.reviewCard.dueCount, 2);
  assert.ok(vm.reviewCard.title.indexOf("2 个考点到期") >= 0);
  assert.strictEqual(vm.reviewCard.title.indexOf("昨天"), -1, "review cycle length is server-owned; no 昨天 claim");
  assert.ok(vm.reviewCard.sub.indexOf("换题验证") >= 0);
  // 任务卡此时自动是验证任务(同一权威,不是复习卡自算的)
  assert.strictEqual(vm.todayTask.task_state, "review_due");
});

// ── 红队 A3 收口:复习卡必须 exact-match 当前任务身份(pack_id+probe_id),
//    禁跨快照身份漂移(卡显示 S05 计数,点击却路由 N01 旧 probe → dead click)。 ──
ok("review card hidden when due snapshot has no exact task identity match", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        // 独立快照里 N01 已完成,只剩 S05 到期 → 与任务身份不匹配,必须隐藏
        due: [{ pack_id: "S05", title: "临时用电三级配电", probe_id: "rvp_s05", retest_available: true }],
      },
    },
    lessons: FULL.lessons,
  });
  assert.strictEqual(vm.reviewCard, null, "cross-snapshot drift must hide the card, never re-pick another due");
});

// 二轮红队 A3:字段缺失/空串身份都不得当成匹配(服务端 resolver 要求非空 + retest_available is True)
ok("review card hidden when due entry omits retest_available (strict === true, no fail-open)", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        // retest_available 缺失 = 供给未知,必须保守隐藏,不得视同可用
        due: [{ pack_id: "N01", title: "网络计划关键线路", probe_id: "rvp_n01" }],
      },
    },
    lessons: FULL.lessons,
  });
  assert.strictEqual(vm.reviewCard, null);
});

ok("blank probe identities never match each other (empty-string equality is a bypass)", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        due: [{ pack_id: "N01", title: "网络计划关键线路", probe_id: "", retest_available: true }],
      },
    },
    lessons: FULL.lessons,
  });
  assert.strictEqual(vm.reviewCard, null, "'' === '' must not count as identity match");
  assert.strictEqual(vm.todayTask.ctaLabel, "", "blank probe is unroutable server-side; no dead-click CTA");
});

ok("review card hidden when the due entry carries a different probe identity", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        due: [{ pack_id: "N01", title: "网络计划关键线路", probe_id: "rvp_other", retest_available: true }],
      },
    },
    lessons: FULL.lessons,
  });
  assert.strictEqual(vm.reviewCard, null);
});

// ── 二轮红队 A5(合法状态误杀恢复):review 路由资格不得复用 forward-only 的
//    lessons light_practice_available(它同时受 LUBAN_LIGHT_PRACTICE_ENABLED 限制);
//    mode=review 的资格 = exact-matched due 条目的 canonical retest_available === true。 ──
ok("review stays routable when light flag is off but the canonical due entry is signed", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01", reason: "到期" } },
    report: {
      ...FULL.report,
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        due: [{ pack_id: "N01", title: "网络计划关键线路", probe_id: "rvp_n01", retest_available: true }],
      },
    },
    lessons: {
      lessons: [
        // LUBAN_LIGHT_PRACTICE_ENABLED=false → lessons 侧 forward 旗标为 false,
        // 但 review module 开着且 due 条目已签发 → 到期验证必须仍可路由
        { pack_id: "N01", title: "网络计划关键线路", light_practice_available: false },
      ],
    },
  });
  assert.strictEqual(vm.todayTask.practice_kind, "retest");
  assert.strictEqual(vm.todayTask.ctaLabel, "开始验证");
  assert.strictEqual(vm.todayTask.mode, "review");
  assert.ok(vm.reviewCard, "legit due verification must not be killed by the forward-only light flag");
  // 轻练旁按钮(forward)仍按 A2 规则在 review_due 下隐藏
  assert.strictEqual(vm.todayTask.light_practice_visible, false);
});

ok("review eligibility degrades honestly when pack_review authority is degraded/unknown", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: { authority: "revalidation_queue", enabled: null, degraded: true,
        due: [{ pack_id: "N01", probe_id: "rvp_n01", retest_available: true }] },
    },
    lessons: FULL.lessons, // lessons 侧 forward 旗标为 true,也不得代替 canonical due 供给
  });
  assert.strictEqual(vm.todayTask.practice_kind, "none", "degraded authority must not borrow the forward flag");
  assert.strictEqual(vm.todayTask.ctaLabel, "");
  assert.ok(vm.todayTask.supplyNote.length > 0, "must explain the honest degrade");
  assert.strictEqual(vm.reviewCard, null);
});

ok("review card hidden when the matched due entry says retest unavailable", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: {
        authority: "revalidation_queue",
        enabled: true,
        due: [{ pack_id: "N01", title: "网络计划关键线路", probe_id: "rvp_n01", retest_available: false }],
      },
    },
    lessons: FULL.lessons,
  });
  assert.strictEqual(vm.reviewCard, null);
});

ok("review card hidden when due list is empty", () => {
  const vm = buildLearnViewModel(FULL); // pack_review.due = []
  assert.strictEqual(vm.reviewCard, null);
});

ok("review card never becomes a second task source when next_step chose another arm", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "practice_active", source_ref: "ti_n01", target_pack_id: "N01", reason: "r" } },
    report: DUE_REPORT, // 有到期,但 server 裁决了 practice_active
    lessons: FULL.lessons,
  });
  assert.strictEqual(vm.reviewCard, null, "review card must follow next_step adjudication, not pack_review");
  assert.strictEqual(vm.todayTask.task_state, "practice_active");
});

ok("review card hidden when pack_review authority is degraded/unknown", () => {
  const degraded = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: { authority: "revalidation_queue", enabled: null, degraded: true, due: [{ pack_id: "N01" }] },
    },
    lessons: FULL.lessons,
  });
  assert.strictEqual(degraded.reviewCard, null);
  const wrongAuthority = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_n01", target_pack_id: "N01" } },
    report: {
      ...FULL.report,
      pack_review: { authority: "frontend_guess", enabled: true, due: [{ pack_id: "N01" }] },
    },
    lessons: FULL.lessons,
  });
  assert.strictEqual(wrongAuthority.reviewCard, null);
});

ok("review card hidden when the review task has no routable retest supply (no dead click)", () => {
  const vm = buildLearnViewModel({
    homeDashboard: { next_step: { mode: "review_due", source_ref: "rvp_a01", target_pack_id: "A01" } },
    report: DUE_REPORT, // due 里没有 A01/rvp_a01 条目 → review 供给不可证 → none
    lessons: FULL.lessons,
  });
  assert.strictEqual(vm.todayTask.practice_kind, "none");
  assert.strictEqual(vm.reviewCard, null);
});

console.log("\nlearn-view-model: " + passed + " passed");
