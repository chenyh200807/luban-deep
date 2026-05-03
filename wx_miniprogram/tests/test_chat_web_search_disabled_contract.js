// test_chat_web_search_disabled_contract.js — chat should not auto-request unconfigured web search
// Run: node wx_miniprogram/tests/test_chat_web_search_disabled_contract.js

var fs = require("fs");
var path = require("path");

var chatJs = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.js"), "utf8");
var chatWxml = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.wxml"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

assert(
  /WEB_SEARCH_AVAILABLE\s*=\s*false/.test(chatJs),
  "chat page should keep web search unavailable from one local constant",
);
assert(
  /if\s*\(\s*WEB_SEARCH_AVAILABLE\s*&&\s*\(this\.data\.enableWebSearch\s*\|\|/.test(chatJs),
  "selected tools should only include web_search when the capability is available",
);
assert(
  !/已自动联网/.test(chatJs),
  "chat page should not show auto web-search success toast while disabled",
);
assert(
  !/时效性问题会自动联网/.test(chatWxml),
  "chat copy should not promise automatic web search while disabled",
);
assert(
  !/联网搜索/.test(chatWxml),
  "chat tool copy should not surface web search when it is closed",
);
assert(
  !/联网搜索/.test(chatJs),
  "chat runtime copy should not surface web search when it is closed",
);

console.log("PASS test_chat_web_search_disabled_contract.js");
