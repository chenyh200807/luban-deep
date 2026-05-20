// test_billing_visual_design_contract.js — billing page should keep the refined visual structure
// Run: node wx_miniprogram/tests/test_billing_visual_design_contract.js

var fs = require("fs");
var path = require("path");

var root = path.join(__dirname, "../..");
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

function checkSurface(label, wxmlPath, wxssPath, expectedLogoPath) {
  var wxml = read(wxmlPath);
  var wxss = read(wxssPath);
  var js = read(wxmlPath.replace(/\.wxml$/, ".js"));

  assert(
    wxml.indexOf('class="nav-logo-shell"') >= 0,
    label + " billing should render the logo inside a stable brand shell",
  );
  assert(
    wxml.indexOf(expectedLogoPath) >= 0,
    label + " billing should use the compact logo mark asset",
  );
  assert(
    wxml.indexOf('class="nav-brand-copy"') >= 0 &&
      wxml.indexOf("额度中心") >= 0,
    label + " billing should pair the mark with explicit brand copy",
  );
  assert(
    wxml.indexOf("选择备考强度") < 0 &&
      wxml.indexOf('class="pkg-grid"') < 0 &&
      wxml.indexOf('class="pay-dock"') < 0 &&
      wxml.indexOf('class="checkout-sheet"') < 0,
    label + " billing should hide the pricing and package selection surface in test builds",
  );
  assert(
    wxml.indexOf("{{item.usageLabel}}") < 0 &&
      wxml.indexOf("{{item.rhythm}}") < 0 &&
      wxml.indexOf("{{item.points}} 智力点") < 0 &&
      wxml.indexOf("当前余额") < 0 &&
      wxml.indexOf("充值额度") < 0,
    label + " billing should not expose package allowance or raw recharge quota copy",
  );
  assert(
    js.indexOf('price: "99"') < 0 &&
      js.indexOf('price: "199"') < 0 &&
      js.indexOf('selectedPkgPrice') < 0 &&
      js.indexOf('createBillingCheckout') < 0,
    label + " billing should not ship default visible package prices while pricing is hidden",
  );
  assert(
    wxml.indexOf('class="usage-quota-list"') >= 0 &&
      wxss.indexOf(".usage-meter-fill") >= 0,
    label + " billing should show usage-limit percentages with reset meters",
  );
  assert(
    wxml.indexOf('class="balance-gauge"') >= 0 &&
      wxss.indexOf(".balance-gauge-ring") >= 0,
    label + " billing should keep the stronger quota dashboard",
  );
  assert(
    wxml.indexOf("额度记录") < 0 &&
      wxml.indexOf("最近流水") < 0 &&
      wxml.indexOf('class="ledger-list"') < 0 &&
      wxml.indexOf('bindtap="onNextPage"') < 0 &&
      js.indexOf("getLedger") < 0 &&
      js.indexOf("_loadLedger") < 0,
    label + " billing should not render or fetch the removed ledger records section",
  );
  assert(
    js.indexOf("微信支付") < 0 &&
      js.indexOf("支付宝") < 0 &&
      wxml.indexOf("确认支付") < 0 &&
      wxml.indexOf("确认开通") < 0 &&
      js.indexOf("暂未开放") < 0 &&
      js.indexOf("暂未开发") < 0 &&
      wxml.indexOf("暂未开放") < 0 &&
      wxml.indexOf("暂未开发") < 0,
    label + " billing should not expose checkout channels while pricing is hidden",
  );
  assert(
    wxss.indexOf(".nav-logo-shell") >= 0 &&
      wxss.indexOf("flex-direction: column") >= 0,
    label + " billing stylesheet should keep the refined logo layout",
  );
  assert(
    wxss.indexOf(".billing-page.light .nav-logo {") < 0,
    label + " billing should not recolor the raw logo with a light-mode filter",
  );
}

(function main() {
  try {
    checkSurface(
      "wx_miniprogram",
      "wx_miniprogram/pages/billing/billing.wxml",
      "wx_miniprogram/pages/billing/billing.wxss",
      "/images/logo-mark-white.png",
    );
    checkSurface(
      "packageDeeptutor",
      "yousenwebview/packageDeeptutor/pages/billing/billing.wxml",
      "yousenwebview/packageDeeptutor/pages/billing/billing.wxss",
      "../../images/logo-mark-white.png",
    );
  } catch (err) {
    fail++;
    errors.push("ERROR: " + (err && err.stack ? err.stack : err));
  }

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_billing_visual_design_contract.js (" + pass + " assertions)");
})();
