// test_package_chat_next_best_action_contract.js — packageDeeptutor next_best_action action loop.
// Run: node yousenwebview/tests/test_package_chat_next_best_action_contract.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass += 1;
    return;
  }
  fail += 1;
  errors.push("FAIL: " + message);
}

var chatJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);
var chatWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
  "utf8",
);

assert(
  /onNextBestActionTap:\s*function/.test(chatJs),
  "[handler] package chat.js must define onNextBestActionTap",
);
var handlerMatch = chatJs.match(/onNextBestActionTap:\s*function[\s\S]*?\n  \},/);
assert(!!handlerMatch, "[handler] can capture onNextBestActionTap body");
var handler = handlerMatch ? handlerMatch[0] : "";
assert(
  handler.indexOf("this._send(") !== -1,
  "[handler] next_best_action tap must reuse the existing _send pipeline",
);
assert(
  handler.indexOf("nba.query") !== -1,
  "[handler] next_best_action tap must prefer the server-projected query",
);
assert(
  handler.indexOf(".slice(0, 80)") !== -1,
  "[guard] legacy target text composed into a fallback prompt must be bounded",
);
assert(
  handler.indexOf("针对我的薄弱点出一道练习题") !== -1,
  "[fallback] legacy next_best_action payloads still need a bounded practice prompt",
);
assert(
  handler.indexOf("isStreaming") !== -1,
  "[guard] active streaming turns must disable next_best_action taps",
);
assert(
  handler.indexOf("nextBestAction") !== -1,
  "[guard] handler must read the server-projected display object on the message",
);
assert(
  /class="nba-go"[^>]*bindtap="onNextBestActionTap"/.test(chatWxml) ||
    /bindtap="onNextBestActionTap"[^>]*class="nba-go"/.test(chatWxml),
  "[wxml] nba-go must bind onNextBestActionTap",
);
assert(
  /class="nba-go"[\s\S]{0,160}data-msgid="\{\{item\.id\}\}"/.test(chatWxml) ||
    /data-msgid="\{\{item\.id\}\}"[\s\S]{0,160}class="nba-go"/.test(chatWxml),
  "[wxml] nba-go must carry the message id",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_package_chat_next_best_action_contract.js (" + pass + " assertions)");
