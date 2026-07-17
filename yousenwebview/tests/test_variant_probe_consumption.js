// 变体判断题消费接线 · 前端契约测试（切片四）
// 断言: retest 页 fact_id 保留 + 错后当场确认(消费点1)入口条件 + 纯导航复用同页。
// Run: node yousenwebview/tests/test_variant_probe_consumption.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var retest = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.js"),
  "utf8",
);
var retestWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.wxml"),
  "utf8",
);
var apiSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/utils/api.js"),
  "utf8",
);

// ── fact_id / probe_role 保留（错题→考点映射的前提；旧实现丢弃）──
assert.ok(
  retest.indexOf("fact_id: String(item.fact_id || \"\")") >= 0,
  "retest item map must preserve server fact_id for the wrong-answer→fact mapping",
);
assert.ok(
  retest.indexOf("probe_role: String(item.probe_role || \"\")") >= 0,
  "retest item map must preserve probe_role",
);

// ── confirm_facts_ready 消费（服务端唯一权威决定入口是否有资格亮）──
assert.ok(
  retest.indexOf("body.confirm_facts_ready") >= 0,
  "retest must read server confirm_facts_ready (single supply authority, never client-derived)",
);

// ── 错后当场确认入口条件: 仅 forward、非 confirm 会话本身、错题 fact ∩ ready ──
assert.ok(
  retest.indexOf('that.data.mode === "forward" && !that.data.isConfirmSession') >= 0,
  "confirm entry must be gated to forward and must not nest inside a confirm session",
);
assert.ok(
  retest.indexOf("readySet[fact]") >= 0,
  "confirm entry facts must be the intersection of wrong-item facts and confirm_facts_ready",
);
assert.ok(
  retest.indexOf("showConfirmEntry: confirmEntryFacts.length > 0") >= 0,
  "confirm entry visibility must derive from the computed intersection (empty ⇒ not shown)",
);

// ── 纯导航复用同页: 新会话 mode=forward&confirm_facts=, 不建第二答题页 ──
assert.ok(
  retest.indexOf("goConfirmFacts") >= 0,
  "retest must expose a goConfirmFacts navigation handler",
);
assert.ok(
  retest.indexOf("&mode=forward&confirm_facts=") >= 0,
  "confirm entry must navigate back into the same retest page as a forward confirm session",
);
assert.strictEqual(
  retest.indexOf("completeLubanRetest") >= 0,
  true,
  "confirm session must reuse the canonical completion endpoint (no second writer)",
);

// ── confirm 会话解析入口: onLoad 从 query 解析 confirm_facts, 归一 isConfirmSession ──
assert.ok(
  retest.indexOf("query.confirm_facts") >= 0,
  "onLoad must parse confirm_facts from the query for a confirm session",
);
assert.ok(
  retest.indexOf("isConfirmSession") >= 0,
  "confirm session flag must exist to prevent confirm-of-confirm nesting",
);
assert.ok(
  retest.indexOf("COPY[isConfirmSession ? \"confirm\" : mode]") >= 0,
  "confirm session must select its own copy variant",
);

// ── wxml: 入口按钮 gated on showConfirmEntry, 绑 goConfirmFacts, 纯导航 catchtap ──
assert.ok(
  retestWxml.indexOf('wx:if="{{showConfirmEntry}}"') >= 0 &&
    retestWxml.indexOf('catchtap="goConfirmFacts"') >= 0,
  "receipt must render the confirm entry only when showConfirmEntry, bound to goConfirmFacts",
);

// ── api.js: confirm_facts 仅 forward 透传（review 场绝不带）──
assert.ok(
  apiSource.indexOf('m === "forward" && confirmFacts ? "&confirm_facts="') >= 0,
  "API must transmit confirm_facts only in forward mode",
);

// ── 项目红线: 入口文案不用"看穿/识破/揭穿/露馅"类审视语气 ──
["看穿", "识破", "揭穿", "露馅"].forEach(function (word) {
  assert.strictEqual(
    retestWxml.indexOf(word),
    -1,
    "confirm entry copy must not use inspecting tone: " + word,
  );
});

console.log("PASS test_variant_probe_consumption.js");
