// test_package_profile_capability_status_contract.js — package profile should not show removed advanced abilities
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

assert(!/capabilityItems:\s*\[/.test(profileJs), "package profile should not declare removed capability availability items");
assert(!/title:\s*"联网搜索"/.test(profileJs), "web search should not appear in unavailable capability items");
assert(!/title:\s*"图片\/文档分析"/.test(profileJs), "file analysis should not appear on package profile");
assert(!/title:\s*"思维导图"/.test(profileJs), "mind map should not appear on package profile");
assert(!/bindtap="onCapabilityTap"/.test(profileWxml), "package profile should not render removed capability rows");
assert(!/扩展能力/.test(profileWxml), "package profile should not render the advanced abilities section");
assert(/\.getWallet\(\)/.test(profileJs), "package profile should own wallet loading");
assert(/\.getLedger\(20\)/.test(profileJs), "package profile should own wallet ledger loading");
assert(/usagePrimaryLabel/.test(profileJs) && /usageRows/.test(profileJs), "package profile should keep usage percentage state");
assert(/_walletPercent\(balance, ledgerRaw\)/.test(profileJs), "package profile should read canonical wallet ledger payload");
assert(/openUsageDetail/.test(profileJs) && /closeUsageDetail/.test(profileJs), "package profile should expose usage detail interactions");
assert(/class="pk-card usage-card"/.test(profileWxml), "package profile should render the usage card (10f paper-ink)");
assert(/class="usage-summary-row"/.test(profileWxml), "package profile should render compact usage rows");
assert(/class="usage-detail-sheet/.test(profileWxml), "package profile should render a usage detail sheet");
assert(!/\{\{points\}\}/.test(profileWxml) && !/\{\{userPoints\}\}/.test(profileWxml), "package profile should not render raw point balances");

// ── 10f 免费档口径：钱包 points 为计费真值，balance<=0 显示静态规则说明 ──
// 后端没有暴露免费额度已用计数的读接口（quota 只在 429 detail / start-turn
// 预约路径出现）——前端绝不自算、绝不绑定动态已用次数。
assert(/freeTier/.test(profileJs), "package profile should derive free tier from wallet balance");
assert(/wx:if="\{\{freeTier\}\}"/.test(profileWxml), "package profile should render the free tier static quota block");
assert(/每日免费提问/.test(profileWxml) && /3 次/.test(profileWxml), "free tier block should state the daily rule");
assert(/12 次/.test(profileWxml), "free tier block should state the weekly rule");
assert(
  !/\{\{[^}]*(todayUsed|weeklyUsed|freeUsed|quotaUsed)[^}]*\}\}/.test(profileWxml),
  "free tier block must not bind fabricated usage counters (no read API exists)",
);

console.log("PASS test_package_profile_capability_status_contract.js");
