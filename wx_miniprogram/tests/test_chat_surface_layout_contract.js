// test_chat_surface_layout_contract.js — chat surface should keep inputs and nav controls reachable
// Run: node wx_miniprogram/tests/test_chat_surface_layout_contract.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function read(rel) {
  return fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
}

var chatWxml = read("pages/chat/chat.wxml");
var chatJs = read("pages/chat/chat.js");
var historyWxml = read("pages/history/history.wxml");
var historyWxss = read("pages/history/history.wxss");
var historyJs = read("pages/history/history.js");

assert(
  (chatWxml.match(/bindfocus="onKeyboardFocus"/g) || []).length >= 2,
  "both hero and bottom textareas should report keyboard focus",
);
assert(
  (chatWxml.match(/bindblur="onKeyboardBlur"/g) || []).length >= 2,
  "both hero and bottom textareas should report keyboard blur",
);
assert(
  (chatWxml.match(/cursor-spacing="\{\{inputCursorSpacing\}\}"/g) || []).length >= 2,
  "textareas should use a stable cursor spacing authority",
);
assert(
  /onKeyboardFocus:\s*function/.test(chatJs) && /onKeyboardBlur:\s*function/.test(chatJs),
  "chat page should expose keyboard layout handlers",
);
assert(
  /bottomBarStyle/.test(chatWxml) && /keyboardHeight/.test(chatJs),
  "fixed bottom input should be positioned from keyboard height",
);
assert(
  /padding-right:\s*\{\{navRightInset\}\}px/.test(historyWxml) &&
    /navRightInset/.test(historyJs),
  "history nav actions should reserve system capsule width",
);
assert(
  /class="nav-action-row"/.test(historyWxml) &&
    /\.nav-action-row/.test(historyWxss) &&
    /navActionRowHeight/.test(historyJs),
  "history management actions should sit below the system capsule row",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_chat_surface_layout_contract.js (" + pass + " assertions)");
