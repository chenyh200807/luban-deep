// test_package_profile_capability_status_contract.js — package profile unavailable abilities
// Run: node yousenwebview/tests/test_package_profile_capability_status_contract.js

var fs = require("fs");
var path = require("path");

var profileJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
  "utf8",
);
var profileWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/profile/profile.wxml"),
  "utf8",
);

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

assert(/capabilityItems:\s*\[/.test(profileJs), "package profile should declare capability availability items");
assert(/title:\s*"联网搜索"[\s\S]*status:\s*"未开放"/.test(profileJs), "web search should be explicit unavailable");
assert(/title:\s*"图片\/文档分析"[\s\S]*status:\s*"未开放"/.test(profileJs), "file analysis should be explicit unavailable");
assert(/title:\s*"思维导图"[\s\S]*status:\s*"未开放"/.test(profileJs), "mind map should be explicit unavailable");
assert(/bindtap="onCapabilityTap"/.test(profileWxml), "capability rows should explain status on tap");

console.log("PASS test_package_profile_capability_status_contract.js");
