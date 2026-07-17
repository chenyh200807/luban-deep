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

// ── 行为级: confirm_facts 编码三形态解析(DevTools 活体死证重放)──
// 死证: goConfirmFacts 曾整串 encodeURIComponent → query 送达 "f1%2Cf2",
// onLoad split(",") 拆不开 → 确认会话 0 题断链(lc-04, 2026-07-17 隔离实验)。
var vmod = require("vm");
var harness = retest + "\n;module.exports.__parseConfirmFacts = parseConfirmFacts;\n";
var sandbox = { module: { exports: {} }, require: function () { return {}; }, Page: function () {}, console: console };
sandbox.exports = sandbox.module.exports;
vmod.runInNewContext(harness, sandbox, { filename: "retest.js" });
var parseConfirmFacts = sandbox.module.exports.__parseConfirmFacts;
assert.strictEqual(typeof parseConfirmFacts, "function", "parseConfirmFacts must be module-scoped for behavioral test");
var FACTS = ["n01-fact-a", "n01-fact-b", "n01-fact-c", "n01-fact-d"];
[
  FACTS.join(","),                                          // 已解码(真机 JSSDK 可能自动解一次)
  encodeURIComponent(FACTS.join(",")),                      // 单次编码(DevTools 死证形态 %2C)
  encodeURIComponent(encodeURIComponent(FACTS.join(","))),  // 双重编码(%252C)
].forEach(function (wire, i) {
  // vm 沙箱 realm 的 Array 原型与本 realm 不同,deepStrictEqual 会误拒 → 串比较
  assert.strictEqual(
    parseConfirmFacts({ confirm_facts: wire }).join("|"),
    FACTS.join("|"),
    "confirm_facts must survive encoding form #" + i,
  );
});
assert.strictEqual(parseConfirmFacts({}).join("|"), "", "empty query → empty facts");
assert.strictEqual(parseConfirmFacts({ confirm_facts: "a,b,c,d,e,f,g" }).length, 5, "≤5 cap holds");
// 发送端不得再整串编码(逗号必须保持字面分隔符)
assert.strictEqual(
  retest.indexOf('encodeURIComponent(facts.join(","))'),
  -1,
  "goConfirmFacts must not whole-string-encode the comma-joined facts (breaks the receiver split)",
);

console.log("PASS test_variant_probe_consumption.js");
