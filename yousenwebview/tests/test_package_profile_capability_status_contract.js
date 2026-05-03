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
assert(!/title:\s*"联网搜索"/.test(profileJs), "web search should not appear in unavailable capability items");
assert(/title:\s*"图片\/文档分析"[\s\S]*status:\s*"未开放"/.test(profileJs), "file analysis should be explicit unavailable");
assert(/title:\s*"思维导图"[\s\S]*status:\s*"未开放"/.test(profileJs), "mind map should be explicit unavailable");
assert(/bindtap="onCapabilityTap"/.test(profileWxml), "capability rows should explain status on tap");
assert(/\.getUsage\(\)/.test(profileJs), "package profile should own usage-limit loading");
assert(/usagePrimaryLabel/.test(profileJs) && /usageRows/.test(profileJs), "package profile should keep usage percentage state");
assert(/quota\.rows/.test(profileJs), "package profile should read canonical quota rows from billing usage payload");
assert(/openUsageDetail/.test(profileJs) && /closeUsageDetail/.test(profileJs), "package profile should expose usage detail interactions");
assert(/class="usage-card glass-card"/.test(profileWxml), "package profile should render the usage card");
assert(/class="usage-summary-row"/.test(profileWxml), "package profile should render compact five-hour and weekly usage rows");
assert(/class="usage-detail-sheet/.test(profileWxml), "package profile should render a usage detail sheet");
assert(!/\{\{points\}\}/.test(profileWxml) && !/\{\{userPoints\}\}/.test(profileWxml), "package profile should not render raw point balances");

console.log("PASS test_package_profile_capability_status_contract.js");
