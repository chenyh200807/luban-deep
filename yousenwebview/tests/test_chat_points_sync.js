// test_chat_points_sync.js — package usage display belongs on profile, not chat
// Run: node yousenwebview/tests/test_chat_points_sync.js

var fs = require("fs");
var path = require("path");

var root = path.join(__dirname, "..");
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

function read(relPath) {
  return fs.readFileSync(path.join(root, relPath), "utf8");
}

var chatJs = read("packageDeeptutor/pages/chat/chat.js");
var chatWxml = read("packageDeeptutor/pages/chat/chat.wxml");
var profileJs = read("packageDeeptutor/pages/profile/profile.js");
var profileWxml = read("packageDeeptutor/pages/profile/profile.wxml");
var profileWxss = read("packageDeeptutor/pages/profile/profile.wxss");

assert(
  chatWxml.indexOf('class="nav-usage-pill"') < 0 &&
    chatWxml.indexOf("{{usagePrimaryLabel}}") < 0 &&
    chatWxml.indexOf('class="billing-drawer"') < 0,
  "chat should not render usage percentage or a usage drawer",
);
assert(
  chatJs.indexOf(".getUsage()") < 0,
  "chat should not fetch usage on bootstrap or stream completion",
);
assert(
  profileJs.indexOf(".getUsage()") >= 0 &&
    profileJs.indexOf("usagePrimaryLabel") >= 0 &&
    profileJs.indexOf("usageRows") >= 0 &&
    profileJs.indexOf("quota.rows") >= 0,
  "profile should own the usage endpoint and state",
);
assert(
  profileWxml.indexOf('class="usage-card glass-card"') >= 0 &&
    profileWxml.indexOf("{{usagePrimaryLabel}}") >= 0 &&
    profileWxml.indexOf('class="usage-summary-row"') >= 0 &&
    profileWxml.indexOf('class="usage-detail-sheet') >= 0 &&
    profileWxml.indexOf('wx:for="{{usageRows}}"') >= 0,
  "profile should render remaining usage summary rows and detail sheet",
);
assert(
  profileWxss.indexOf(".usage-meter-fill") >= 0 &&
    profileWxss.indexOf(".usage-action") >= 0,
  "profile should style usage meters and the recharge action",
);
assert(
  profileWxml.indexOf("{{points}}") < 0 &&
    profileWxml.indexOf("{{userPoints}}") < 0,
  "profile should not show raw point balances",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_chat_points_sync.js (" + pass + " assertions)");
