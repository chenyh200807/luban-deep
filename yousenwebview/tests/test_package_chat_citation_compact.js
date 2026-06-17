const assert = require("assert");
const fs = require("fs");
const path = require("path");

const citationFormat = require("../packageDeeptutor/utils/citation-format");

const ROOT = path.resolve(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const formatted = citationFormat.formatCitations([
  {
    marker: "〔1〕",
    source_type: "textbook",
    title: "2026 建筑实务教材：建筑物的构成体系",
    locator: "第1章 建筑工程设计技术 · p.2",
    public_quote:
      "建筑物由结构体系、围护体系和设备体系组成，结构体系承受竖向和侧向荷载。",
  },
]);

assert.strictEqual(formatted.length, 1);
assert.strictEqual(formatted[0].key, "1");
assert.strictEqual(formatted[0].title, "2026 建筑实务教材：建筑物的构成体系");
assert.strictEqual(formatted[0].locator, "第1章 建筑工程设计技术 · p.2");
assert.strictEqual(formatted[0].quoteExpanded, false);
assert.strictEqual(formatted[0].quoteActionText, "查看摘录");
assert.ok(formatted[0].quote.indexOf("建筑物由结构体系") >= 0);

const wxml = read("packageDeeptutor/pages/chat/chat.wxml");
assert.ok(
  wxml.indexOf("bindtap=\"onToggleCitationQuote\"") >= 0,
  "citation quote should be behind an explicit expand action",
);
assert.ok(
  /cite-quote[\s\S]*wx:if="\{\{ct\.quote && ct\.quoteExpanded\}\}"/.test(wxml),
  "long quote should render only when the citation is expanded",
);
assert.ok(
  wxml.indexOf("{{ct.quoteActionText}}") >= 0,
  "citation action should expose a compact expand/collapse label",
);

const wxss = read("packageDeeptutor/pages/chat/chat.wxss");
assert.ok(
  wxss.indexOf(".cite-toggle") >= 0,
  "compact reference block should style the quote toggle separately",
);

const js = read("packageDeeptutor/pages/chat/chat.js");
assert.ok(
  js.indexOf("onToggleCitationQuote") >= 0 &&
    js.indexOf("quoteExpanded") >= 0 &&
    js.indexOf("quoteActionText") >= 0,
  "chat page should implement citation quote expand/collapse state",
);

console.log("package chat compact citation contract ok");
