// test_package_chat_home_actions.js — package chat hero should keep secondary actions discoverable but not noisy
// Run: node yousenwebview/tests/test_package_chat_home_actions.js

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

var chatJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);
var chatWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
  "utf8",
);
var chatWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxss"),
  "utf8",
);

assert(
  chatWxml.indexOf("class=\"points-pill\"") >= 0 &&
    chatWxml.indexOf("{{userPoints}}") >= 0,
  "hero should keep the points balance visible as the only always-on status shortcut",
);
assert(
  chatWxml.indexOf("class=\"hero-more-btn\"") >= 0 &&
    chatJs.indexOf("onHeroMoreActions") >= 0,
  "hero secondary actions should be consolidated behind a more menu",
);
assert(
  chatWxml.indexOf("class=\"home-entry-btn\"") < 0 &&
    chatWxml.indexOf("class=\"row-icon-btn\" bindtap=\"onToggleTheme\"") < 0 &&
    chatWxml.indexOf("class=\"row-icon-btn\" bindtap=\"goRecharge\"") < 0 &&
    chatWxml.indexOf("class=\"avatar\" wx:if=\"{{profileEnabled}}\"") < 0,
  "hero should not expose ambiguous same-weight icon shortcuts",
);
assert(
  chatJs.indexOf("返回佑森首页") >= 0 &&
    chatJs.indexOf("充值中心") >= 0 &&
    chatJs.indexOf("个人中心") >= 0,
  "more menu should preserve the previous secondary destinations",
);
assert(
  chatWxss.indexOf(".hero-more-btn") >= 0 &&
    chatWxss.indexOf(".hero-more-dot") >= 0,
  "more menu should have an explicit touch target style",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_chat_home_actions.js (" + pass + " assertions)");
