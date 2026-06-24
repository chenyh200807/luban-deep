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

function checkSurface(label, wxmlPath, wxssPath, expectedLogoPath, options) {
  var opts = options || {};
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
      wxml.indexOf("权益中心") >= 0,
    label + " billing should pair the mark with explicit brand copy",
  );
  if (opts.expectPackages) {
    assert(
      wxml.indexOf('class="pkg-grid"') >= 0 &&
        wxml.indexOf('class="pay-dock"') >= 0 &&
        wxml.indexOf('class="contact-sales-sheet"') >= 0 &&
        js.indexOf("contactSalesVisible") >= 0,
      label + " billing should expose package selection and sales contact QR flow",
    );
  } else {
    assert(
      wxml.indexOf('class="pkg-grid"') < 0 &&
        wxml.indexOf('class="pay-dock"') < 0 &&
        wxml.indexOf('class="contact-sales-sheet"') < 0,
      label + " billing should keep the lightweight entitlement dashboard",
    );
  }
  assert(
    wxml.indexOf("{{item.rhythm}}") < 0 &&
      wxml.indexOf("{{item.points}} 智力点") < 0 &&
      wxml.indexOf("当前余额") < 0 &&
      wxml.indexOf("充值额度") < 0,
    label + " billing should not expose raw internal point or quota copy",
  );
  if (opts.expectPackages) {
    assert(
      js.indexOf('price: "198"') >= 0 &&
        js.indexOf('price: "598"') >= 0 &&
        js.indexOf('price: "998"') >= 0 &&
        js.indexOf('price: "99"') < 0 &&
        js.indexOf('price: "199"') < 0 &&
        js.indexOf('selectedPkgPrice') < 0,
      label + " billing should pin launch package prices and avoid stale pricing",
    );
  } else {
    assert(
      js.indexOf('price: "99"') < 0 &&
        js.indexOf('price: "199"') < 0 &&
        js.indexOf('selectedPkgPrice') < 0 &&
        js.indexOf('createBillingCheckout') < 0,
      label + " billing should not ship package prices on the lightweight surface",
    );
  }
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
    wxml.indexOf("使用记录") >= 0 &&
      wxml.indexOf('class="ledger-card"') >= 0 &&
      wxml.indexOf("{{item.usageLabel}}") >= 0 &&
      wxml.indexOf("{{item.balanceLabel}}") >= 0 &&
      js.indexOf("getLedger") >= 0 &&
      wxml.indexOf("额度记录") < 0 &&
      wxml.indexOf("最近流水") < 0 &&
      wxml.indexOf('bindtap="onNextPage"') < 0 &&
      js.indexOf("_loadLedger") < 0,
    label + " billing should render ledger-backed usage records without legacy paging copy",
  );
  if (opts.expectPackages) {
    assert(
      wxml.indexOf("联系销售开通") >= 0 &&
        wxml.indexOf("sales-contact-qr.png") >= 0 &&
        js.indexOf("createBillingCheckout") < 0 &&
        js.indexOf("requestPayment") < 0 &&
        js.indexOf("暂未开发") < 0 &&
        wxml.indexOf("暂未开发") < 0,
      label + " billing should show the sales contact QR before any direct payment path",
    );
  } else {
    assert(
      js.indexOf("微信支付") < 0 &&
        js.indexOf("支付宝") < 0 &&
        wxml.indexOf("确认支付") < 0 &&
        wxml.indexOf("确认开通") < 0 &&
        js.indexOf("暂未开放") < 0 &&
        js.indexOf("暂未开发") < 0 &&
        wxml.indexOf("暂未开放") < 0 &&
        wxml.indexOf("暂未开发") < 0,
      label + " billing should not expose checkout controls on the lightweight surface",
    );
  }
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
      { expectPackages: false },
    );
    checkSurface(
      "packageDeeptutor",
      "yousenwebview/packageDeeptutor/pages/billing/billing.wxml",
      "yousenwebview/packageDeeptutor/pages/billing/billing.wxss",
      "../../images/logo-mark-white.png",
      { expectPackages: true },
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
