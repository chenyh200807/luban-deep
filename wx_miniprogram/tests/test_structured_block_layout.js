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
var packageChatJs = fs.readFileSync(
  path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);
var packageWsStream = fs.readFileSync(
  path.join(__dirname, "../../yousenwebview/packageDeeptutor/utils/ws-stream.js"),
  "utf8",
);
var wxWsStream = fs.readFileSync(
  path.join(__dirname, "../utils/ws-stream.js"),
  "utf8",
);
var chatWxml = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.wxml"),
  "utf8",
);
var packageChatWxml = fs.readFileSync(
  path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/chat/chat.wxml"),
  "utf8",
);
var chatWxss = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.wxss"),
  "utf8",
);
var packageChatWxss = fs.readFileSync(
  path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/chat/chat.wxss"),
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

function packageHasSelector(selector) {
  return packageChatWxss.indexOf(selector) >= 0;
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
  chatJs.indexOf('typeof d.response === "string"') >= 0 &&
    chatJs.indexOf("parseBlocks: true") >= 0,
  "chat.js should let terminal result.response replace provisional streaming text",
);
assert(
  packageChatJs.indexOf('typeof d.response === "string"') >= 0 &&
    packageChatJs.indexOf("parseBlocks: true") >= 0,
  "packageDeeptutor chat.js should mirror terminal result.response replacement",
);
assert(
  wxWsStream.indexOf("buildFinalResponseEvent") >= 0 &&
    packageWsStream.indexOf("buildFinalResponseEvent") >= 0,
  "both ws-stream surfaces should forward public result.response to onFinal",
);
assert(
  chatWxml.indexOf("cite-head-sub") >= 0 &&
    chatWxml.indexOf("References") >= 0 &&
    chatWxml.indexOf("ct.locator") >= 0 &&
    chatWxml.indexOf("ct.quote") >= 0,
  "wx_miniprogram chat.wxml should render structured references at the message tail",
);
assert(
  packageChatWxml.indexOf("cite-head-sub") >= 0 &&
    packageChatWxml.indexOf("References") >= 0 &&
    packageChatWxml.indexOf("ct.locator") >= 0 &&
    packageChatWxml.indexOf("ct.quote") >= 0,
  "packageDeeptutor chat.wxml should mirror structured references at the message tail",
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
assert(
  chatWxml.indexOf("b.mobileStrategy==='compact_cards'") >= 0 &&
    chatWxml.indexOf("row[colIndex] ? row[colIndex].nodes : []") >= 0,
  "markdown tables should support compact cards strategy",
);
assert(hasSelector(".md-steps"), "wxss should style steps cards");
assert(hasSelector(".md-step"), "wxss should style step rows");
assert(hasSelector(".md-recap"), "wxss should style recap cards");
assert(hasSelector(".md-chart"), "wxss should style chart cards");
assert(hasSelector(".md-chart-fallback-title"), "wxss should style chart fallback title");
assert(hasSelector(".md-chart-strategy"), "wxss should style chart fallback helper copy");
assert(
  hasSelector(".cite-locator") && hasSelector(".cite-quote"),
  "wx_miniprogram wxss should style citation locator and quote rows",
);
assert(
  packageHasSelector(".cite-locator") && packageHasSelector(".cite-quote"),
  "packageDeeptutor wxss should style citation locator and quote rows",
);
assert(
  hasSelector(".page.light .md-chart") && hasSelector(".page.light .md-recap"),
  "light theme should preserve structured block styling",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_structured_block_layout.js (" + pass + " assertions)");
