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
      wxml.indexOf("充值中心") >= 0,
    label + " billing should pair the mark with explicit brand copy",
  );
  assert(
    wxml.indexOf('class="pkg-name"') >= 0 &&
      wxml.indexOf('class="pkg-desc"') >= 0 &&
      wxml.indexOf('class="pkg-check {{selectedPkg === item.id ?') >= 0,
    label + " billing packages should be a selectable list with names, descriptions, and selection affordance",
  );
  assert(
    wxml.indexOf("{{item.usageLabel}}") >= 0 &&
      wxml.indexOf("{{item.points}} 智力点") < 0 &&
      wxml.indexOf("当前余额") < 0 &&
      wxml.indexOf("充值额度") < 0,
    label + " billing should describe packages as usage allowance rather than raw points or recharge quota",
  );
  assert(
    wxml.indexOf('class="usage-quota-list"') >= 0 &&
      wxss.indexOf(".usage-meter-fill") >= 0,
    label + " billing should show usage-limit percentages with reset meters",
  );
  assert(
    wxss.indexOf(".nav-logo-shell") >= 0 &&
      wxss.indexOf(".pkg-grid") >= 0 &&
      wxss.indexOf("flex-direction: column") >= 0,
    label + " billing stylesheet should keep the refined logo and vertical package layout",
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
