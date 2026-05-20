// test_profile_capability_status_contract.js — profile should not show removed advanced abilities
// Run: node wx_miniprogram/tests/test_profile_capability_status_contract.js

var fs = require("fs");
var path = require("path");

var profileJs = fs.readFileSync(path.join(__dirname, "../pages/profile/profile.js"), "utf8");
var profileWxml = fs.readFileSync(path.join(__dirname, "../pages/profile/profile.wxml"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

assert(!/capabilityItems:\s*\[/.test(profileJs), "profile should not declare removed capability availability items");
assert(!/title:\s*"联网搜索"/.test(profileJs), "web search should not appear in unavailable capability items");
assert(!/title:\s*"图片\/文档分析"/.test(profileJs), "file analysis should not appear on profile");
assert(!/title:\s*"思维导图"/.test(profileJs), "mind map should not appear on profile");
assert(!/bindtap="onCapabilityTap"/.test(profileWxml), "profile should not render removed capability rows");
assert(!/扩展能力/.test(profileWxml), "profile should not render the advanced abilities section");
assert(/\.getUsage\(\)/.test(profileJs), "profile should own usage-limit loading");
assert(/usagePrimaryLabel/.test(profileJs) && /usageRows/.test(profileJs), "profile should keep usage percentage state");
assert(/quota\.rows/.test(profileJs), "profile should read canonical quota rows from billing usage payload");
assert(/openUsageDetail/.test(profileJs) && /closeUsageDetail/.test(profileJs), "profile should expose usage detail interactions");
assert(/class="usage-card glass-card"/.test(profileWxml), "profile should render the usage card");
assert(/class="usage-summary-row"/.test(profileWxml), "profile should render compact visible usage rows");
assert(/five_hour/.test(profileJs) && /!== "five_hour"/.test(profileJs), "profile should keep five-hour quota as backend-only protection");
assert(/class="usage-detail-sheet/.test(profileWxml), "profile should render a usage detail sheet");
assert(!/\{\{points\}\}/.test(profileWxml) && !/\{\{userPoints\}\}/.test(profileWxml), "profile should not render raw point balances");

console.log("PASS test_profile_capability_status_contract.js");
