// Run: node yousenwebview/tests/test_experience_billing_contract.js

var fs = require("fs");
var path = require("path");

var root = path.join(__dirname, "..", "packageDeeptutor");
var api = require(path.join(root, "utils", "api"));
var js = fs.readFileSync(path.join(root, "pages", "billing", "billing.js"), "utf8");
var wxml = fs.readFileSync(path.join(root, "pages", "billing", "billing.wxml"), "utf8");

if (typeof api.getExperienceStatus !== "function" || typeof api.redeemExperience !== "function") {
  throw new Error("billing real entry must consume server-authoritative experience APIs");
}
if (
  js.indexOf("data.video_access_limit") < 0 ||
  js.indexOf("experienceVideoAccessLabel") < 0 ||
  wxml.indexOf("{{experienceVideoAccessLabel}}") < 0 ||
  wxml.indexOf("experienceExpiresLabel") < 0
) {
  throw new Error("billing entry must consume and render the server video entitlement and expiry");
}
if (js.indexOf("30 个精选核心视频") >= 0 || wxml.indexOf("30 个精选核心视频") >= 0) {
  throw new Error("billing entry must not hard-code the invite video entitlement");
}
["剩余预算", "成本额度", "1 CNY", "0.8 CNY", "剩余次数"].forEach(function (forbidden) {
  if (js.indexOf(forbidden) >= 0 || wxml.indexOf(forbidden) >= 0) {
    throw new Error("learner experience UI must not expose internal cost/count copy: " + forbidden);
  }
});

console.log("PASS test_experience_billing_contract.js");
