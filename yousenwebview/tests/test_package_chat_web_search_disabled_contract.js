// test_package_chat_web_search_disabled_contract.js — package chat can explicitly request configured web search
// Run: node yousenwebview/tests/test_package_chat_web_search_disabled_contract.js

var fs = require("fs");
var path = require("path");

var chatJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);
var chatWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
  "utf8",
);
var apiJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/utils/api.js"),
  "utf8",
);

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

assert(
  !/WEB_SEARCH_AVAILABLE\s*=\s*true/.test(chatJs),
  "package chat must not hardcode web search availability",
);
assert(
  /getRuntimeCapabilities/.test(apiJs),
  "package chat api should expose backend runtime capabilities",
);
assert(
  /getRuntimeCapabilities[\s\S]*noAuth:\s*true/.test(apiJs),
  "package chat api should read public runtime capabilities without auth side effects",
);
assert(
  /webSearchAvailable:\s*DEFAULT_WEB_SEARCH_AVAILABLE/.test(chatJs),
  "package chat should default web search to unavailable until backend confirms it",
);
assert(
  /if\s*\(\s*this\._isWebSearchAvailable\(\)\s*&&\s*\(this\.data\.enableWebSearch\s*\|\|/.test(chatJs),
  "selected tools should only include web_search when backend capability is available",
);
assert(
  /current_info_required:\s*true/.test(chatJs),
  "explicit web search must set current_info_required for the mobile turn adapter",
);
assert(
  /nextWebSearch \? "本轮可联网" : "已关闭联网"/.test(chatJs),
  "package chat should give explicit feedback when users toggle web search",
);
assert(
  /wx:if="\{\{webSearchAvailable\}\}"\s+class="web-pill \{\{enableWebSearch\?'on':''\}\}"/.test(chatWxml),
  "package chat should render the web-search pill only when backend capability is available",
);
assert(
  /<text class="web-pill-txt">联网<\/text>/.test(chatWxml),
  "package chat web-search pill should use the requested 联网 label",
);
assert(
  !/该能力暂未开放/.test(chatJs),
  "package chat should no longer present web search as closed",
);

console.log("PASS test_package_chat_web_search_disabled_contract.js");
