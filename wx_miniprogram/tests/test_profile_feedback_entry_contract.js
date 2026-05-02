// test_profile_feedback_entry_contract.js — profile should expose native product feedback entry
// Run: node wx_miniprogram/tests/test_profile_feedback_entry_contract.js

var fs = require("fs");
var path = require("path");

var profileJs = fs.readFileSync(
  path.join(__dirname, "../pages/profile/profile.js"),
  "utf8",
);
var profileWxml = fs.readFileSync(
  path.join(__dirname, "../pages/profile/profile.wxml"),
  "utf8",
);
var profileWxss = fs.readFileSync(
  path.join(__dirname, "../pages/profile/profile.wxss"),
  "utf8",
);

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

assert(
  /id:\s*["']feedback["'][\s\S]*title:\s*["']意见反馈["'][\s\S]*nativeOpenType:\s*["']feedback["']/.test(
    profileJs,
  ),
  "profile linkItems should include a native feedback item",
);
assert(
  /open-type="{{item\.nativeOpenType}}"/.test(profileWxml),
  "profile feedback item should use native open-type binding",
);
assert(
  /wx:else[\s\S]*bindtap="openLink"/.test(profileWxml),
  "non-native profile links should keep existing openLink routing",
);
assert(
  /\.link-row-button::after\s*\{\s*border:\s*0;\s*\}/.test(profileWxss),
  "native feedback button should reset default button border",
);

console.log("PASS test_profile_feedback_entry_contract.js");
