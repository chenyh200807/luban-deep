// Run: node yousenwebview/tests/test_concept_cards_view_model.js
// 考点卡库/翻卡页视图模型域测试:
// 1. 库总览: 张数只来自服务端 signed 卡池投影, 拿不到/旗标关 → 不可用(占位);
// 2. 卡组: 字段逐字透传 + point_id/页码角注; 无 quote/front 的脏卡 fail-closed 剔除;
// 3. 牌序: 纯本地 immutable(记住了前进/再看一眼挪队尾), 页面零掌握上报;
// 4. 复习页入口: conceptCardsAvailable 单一判定点(0 张/降级 null 一律占位);
// 5. 文案铁律: 考点卡面禁审视揭短词。
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var ccvm = require("../packageDeeptutor/utils/concept-cards-view-model.js");
var reviewVm = require("../packageDeeptutor/utils/review-view-model.js");

// ── 1. 库总览投影 ─────────────────────────────────────────────
var lib = ccvm.buildLibraryViewModel({
  total: 13,
  enabled: true,
  packs: [
    { pack_id: "s05", title: "临时用电三级配电", card_count: 11 },
    { pack_id: "F16", title: "屋面防水起鼓割补", card_count: 2 },
    { pack_id: "X99", title: "零卡站", card_count: 0 }, // 零卡站不出条
  ],
});
assert.strictEqual(lib.available, true);
assert.strictEqual(lib.total, 13);
assert.strictEqual(lib.packs.length, 2);
assert.strictEqual(lib.packs[0].packId, "S05");

// 旗标关/降级: 空投影 → 不可用(复习页保持「即将开通」)
assert.strictEqual(ccvm.buildLibraryViewModel({ total: 0, packs: [], enabled: false }).available, false);
assert.strictEqual(ccvm.buildLibraryViewModel(null).available, false);

// ── 2. 卡组投影: 逐字透传 + fail-closed 剔脏卡 ───────────────
var deck = ccvm.buildDeckViewModel({
  pack_id: "S05",
  title: "临时用电三级配电",
  cards: [
    {
      card_id: "S05:kc:1A431011_015_0016:1",
      front: "送电/停电顺序",
      key_gist: "送电：总→分→开；停电：开→分→总",
      quote: "送电顺序：总配电箱 → 分配电箱 → 开关箱；停电顺序：开关箱 → 分配电箱 → 总配电箱。",
      point_id: "kc:1A431011_015_0016:1",
      source_ref: { chunk_id: "1A431011_015_0016", page_num: 15 },
    },
    { card_id: "S05:bad", front: "无原文的脏卡", quote: "", point_id: "kc:x" },
  ],
});
assert.strictEqual(deck.packId, "S05");
assert.strictEqual(deck.cards.length, 1, "无 quote 的脏卡必须 fail-closed 剔除");
var card = deck.cards[0];
assert.strictEqual(
  card.quote,
  "送电顺序：总配电箱 → 分配电箱 → 开关箱；停电顺序：开关箱 → 分配电箱 → 总配电箱。",
  "教材原文必须逐字透传",
);
assert.strictEqual(card.sourceNote, "kc:1A431011_015_0016:1 · 教材 P15");
assert.ok(card.prompt, "正面问法 = 固定模板(确定性渲染)");

// ── 3. 牌序纯函数: immutable + again 挪队尾 ──────────────────
var s0 = ccvm.initDeckState(3);
assert.deepStrictEqual(s0.order, [0, 1, 2]);
assert.strictEqual(ccvm.currentCardIndex(s0), 0);

var s1 = ccvm.stepDeck(s0, "again"); // 0 号挪队尾
assert.deepStrictEqual(s0.order, [0, 1, 2], "stepDeck 不得改入参(immutable)");
assert.deepStrictEqual(s1.order, [1, 2, 0]);
assert.strictEqual(ccvm.currentCardIndex(s1), 1);
assert.strictEqual(s1.againCount, 1);

var s2 = ccvm.stepDeck(s1, "got_it");
var s3 = ccvm.stepDeck(s2, "got_it");
var s4 = ccvm.stepDeck(s3, "got_it");
assert.strictEqual(ccvm.currentCardIndex(s4), -1, "过完即完场");
assert.strictEqual(s4.gotCount, 3);
assert.strictEqual(ccvm.stepDeck(s4, "got_it"), s4, "完场后步进为 no-op");

// ── 4. 复习页入口单一判定点 ──────────────────────────────────
var built = reviewVm.buildReviewViewModel({
  lessons: { lessons: [{ pack_id: "S05", title: "临时用电" }] },
  reviewDue: { due: [], learned_count: 1 },
  mistakeBook: null,
  conceptCards: { total: 13, packs: [{ pack_id: "S05", card_count: 13 }], enabled: true },
});
assert.strictEqual(built.conceptCardsAvailable, true);
assert.strictEqual(built.conceptCardTotal, 13);
// 降级 null / 旗标关 total=0 → 占位(不造数)
[null, { total: 0, packs: [], enabled: false }].forEach(function (bodyCase) {
  var degraded = reviewVm.buildReviewViewModel({
    lessons: { lessons: [] },
    reviewDue: { due: [] },
    conceptCards: bodyCase,
  });
  assert.strictEqual(degraded.conceptCardsAvailable, false);
  assert.strictEqual(degraded.conceptCardTotal, 0);
});

// ── 5. 文案铁律: 考点卡面禁审视揭短词 ────────────────────────
var FORBIDDEN = ["看穿", "识破", "揭穿", "露馅", "拆穿"];
var surfaces = [
  path.join(__dirname, "../packageDeeptutor/utils/concept-cards-view-model.js"),
  path.join(__dirname, "../packageDeeptutor/pages/luban/concept-cards/concept-cards.js"),
  path.join(__dirname, "../packageDeeptutor/pages/luban/concept-cards/concept-cards.wxml"),
  path.join(__dirname, "../packageDeeptutor/pages/luban/concept-cards/concept-cards.wxss"),
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

// ── 6. 回归防线: 翻卡页零掌握写入(无 learner-signal / 判分调用) ─
var pageJs = fs.readFileSync(surfaces[1], "utf8");
["postStationCompleted", "postLessonProgress", "learner-signal", "mastery"].forEach(
  function (token) {
    assert.strictEqual(
      pageJs.indexOf(token),
      -1,
      "concept-cards.js 出现写入痕迹「" + token + "」——两按钮必须纯本地",
    );
  },
);

console.log("test_concept_cards_view_model: all assertions passed");

// ── 记忆面结构化(2026-07-12): 确定性解析,零改写零生成 ──
(function () {
  var GIST = "勘察→设计→施工竣工报告→监理预验收评估→建设单位正式验收";
  var QUOTE =
    "单位工程完工后，各相关单位应按下列要求进行工程竣工验收： ① 勘察单位应编制勘察工程质量检查报告； ② 设计单位应对设计变更进行检查； ③ 施工单位应自检合格； ④ 监理单位应在自检合格后组织预验收，14天内完成； ⑤ 建设单位应组织竣工验收。";
  var st = ccvm.buildCardStructure({ keyGist: GIST, quote: QUOTE });

  assert(st.chain && st.chain.length === 5, "gist 箭头链切成 5 步");
  assert(st.chain.join("→") === GIST, "链步逐字还原=gist(零改写)");

  assert(st.roster && st.roster.length === 5, "quote ①-⑤ 切成 5 行");
  assert(st.roster[0].actor === "勘察单位", "主体签章提取");
  st.roster.forEach(function (r) {
    assert(QUOTE.indexOf(r.actor + r.body) >= 0, "主体+动作=原文逐字子串: " + r.actor);
  });

  assert(st.numbers.length === 1 && st.numbers[0].num === "14" && st.numbers[0].unit === "天", "关键数提取14天");
  assert(!st.plain, "有结构不回落");

  var stPlain = ccvm.buildCardStructure({ keyGist: "防水层施工要点", quote: "屋面防水应按规范施工。" });
  assert(stPlain.plain === true && !stPlain.chain && !stPlain.roster, "无结构回落颗粒条");

  var deck = ccvm.buildDeckViewModel({ pack_id: "a01", title: "T", cards: [{ card_id: "c1", front: "f", key_gist: GIST, quote: QUOTE, point_id: "kc:x", source_ref: { page_num: 21 } }] });
  assert(deck.cards[0].structure && deck.cards[0].structure.chain.length === 5, "deck 卡挂 structure");
  console.log("PASS 记忆面结构化 8 断言");
})();
