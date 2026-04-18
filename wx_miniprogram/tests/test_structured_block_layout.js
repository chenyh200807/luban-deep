// test_structured_block_layout.js — regression checks for structured teaching blocks
// Run: node wx_miniprogram/tests/test_structured_block_layout.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

var chatJs = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.js"),
  "utf8",
);
var chatWxml = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.wxml"),
  "utf8",
);
var chatWxss = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.wxss"),
  "utf8",
);

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function hasSelector(selector) {
  return chatWxss.indexOf(selector) >= 0;
}

assert(
  /debugReplaceMessagesWithStructuredSample\s*:\s*function/.test(chatJs),
  "chat.js should expose a devtools fixture injection helper",
);
assert(
  /debugListMarkdownRegressionSamples\s*:\s*function/.test(chatJs),
  "chat.js should expose a devtools markdown sample listing helper",
);
assert(
  /debugLoadMarkdownRegressionSample\s*:\s*function/.test(chatJs),
  "chat.js should expose a devtools markdown sample loader",
);
assert(
  chatWxml.indexOf("b.type==='steps' && b.isStructured") >= 0,
  "chat.wxml should render structured steps blocks",
);
assert(
  chatWxml.indexOf("b.type==='recap' && b.isStructured") >= 0,
  "chat.wxml should render structured recap blocks",
);
assert(
  chatWxml.indexOf("b.type==='chart' && b.isStructured") >= 0,
  "chat.wxml should render structured chart blocks",
);
assert(
  chatWxml.indexOf("wx:elif=\"{{b.type==='table' && b.isStructured}}\"") >= 0,
  "structured table branch should stay in the main wx:elif chain to avoid duplicate heading rendering",
);
assert(
  chatWxml.indexOf("图形不可用时回退为数据表") >= 0,
  "chart fallback copy should remain visible in template",
);
assert(
  chatWxml.indexOf("b.fallbackTable.mobileStrategy==='compact_cards'") >= 0,
  "chart fallback table should support compact cards strategy",
);
assert(hasSelector(".md-steps"), "wxss should style steps cards");
assert(hasSelector(".md-step"), "wxss should style step rows");
assert(hasSelector(".md-recap"), "wxss should style recap cards");
assert(hasSelector(".md-chart"), "wxss should style chart cards");
assert(hasSelector(".md-chart-fallback-title"), "wxss should style chart fallback title");
assert(hasSelector(".md-chart-strategy"), "wxss should style chart fallback helper copy");
assert(
  hasSelector(".page.light .md-chart") && hasSelector(".page.light .md-recap"),
  "light theme should preserve structured block styling",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_structured_block_layout.js (" + pass + " assertions)");
