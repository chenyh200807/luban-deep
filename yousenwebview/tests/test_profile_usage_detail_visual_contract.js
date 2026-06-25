// test_profile_usage_detail_visual_contract.js - profile usage detail sheet must stay readable in light mode.
// Run: node yousenwebview/tests/test_profile_usage_detail_visual_contract.js

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

var profileDir = path.join(__dirname, "../packageDeeptutor/pages/profile");
var wxml = fs.readFileSync(path.join(profileDir, "profile.wxml"), "utf8");
var wxss = fs.readFileSync(path.join(profileDir, "profile.wxss"), "utf8");

assert(
  wxml.indexOf('class="usage-detail-sheet {{usageDetailShow ?') >= 0,
  "profile should render a usage detail sheet",
);
assert(
  wxml.indexOf('style="{{item.barStyle}}"') >= 0,
  "usage detail meter fill should bind to item.barStyle",
);
assert(
  /\.profile-page\.light\s+\.usage-detail-sheet\s*\{/.test(wxss),
  "light mode should override usage detail sheet surface",
);
assert(
  /\.profile-page\.light\s+\.usage-detail-sheet\s+\.usage-meter-fill\s*\{[^}]*linear-gradient/.test(wxss),
  "light mode detail sheet should keep an accented progress fill",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_profile_usage_detail_visual_contract.js (" + pass + " assertions)");
