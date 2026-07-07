var fs = require("fs");
var path = require("path");

var roots = [
  {
    wxss: path.join(__dirname, "../pages/login/login.wxss"),
    wxml: path.join(__dirname, "../pages/login/login.wxml"),
    js: path.join(__dirname, "../pages/login/login.js"),
    json: path.join(__dirname, "../pages/login/login.json"),
    rootClass: "scene",
    lightSelector: "\\.scene\\.light",
  },
  {
    wxss: path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/login/login.wxss"),
    wxml: path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/login/login.wxml"),
    js: path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/login/login.js"),
    json: path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/login/login.json"),
    rootClass: "scene",
    lightSelector: "\\.scene\\.light",
  },
  {
    wxss: path.join(__dirname, "../pages/login/manual.wxss"),
    wxml: path.join(__dirname, "../pages/login/manual.wxml"),
    js: path.join(__dirname, "../pages/login/manual.js"),
    json: path.join(__dirname, "../pages/login/manual.json"),
    rootClass: "manual-page",
    lightSelector: "\\.manual-page\\.light",
  },
  {
    wxss: path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/login/manual.wxss"),
    wxml: path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/login/manual.wxml"),
    js: path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/login/manual.js"),
    json: path.join(__dirname, "../../yousenwebview/packageDeeptutor/pages/login/manual.json"),
    rootClass: "manual-page",
    lightSelector: "\\.manual-page\\.light",
  },
];

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

function blockFor(css, selector) {
  var escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  var match = css.match(new RegExp(escaped + "\\s*\\{([\\s\\S]*?)\\}"));
  return match ? match[1] : "";
}

roots.forEach(function (files) {
  var css = fs.readFileSync(files.wxss, "utf8");
  var wxml = fs.readFileSync(files.wxml, "utf8");
  var js = fs.readFileSync(files.js, "utf8");
  var config = JSON.parse(fs.readFileSync(files.json, "utf8"));
  var primary = blockFor(css, ".btn-wechat-primary");
  var privacyButton = blockFor(css, ".privacy-consent-button,\n.privacy-consent-toggle");

  if (primary) {
    assert(
      /background:\s*transparent\s*!important;/.test(primary),
      files.wxss + " should keep the native button surface transparent",
    );
  }
  if (wxml.indexOf("privacy-consent-button") >= 0) {
    assert(
      /hero-line-single/.test(wxml) && /hero-line-single/.test(css),
      files.wxml + " should keep the compact one-line login headline",
    );
    assert(
      /background:\s*transparent\s*!important;/.test(privacyButton),
      files.wxss + " should keep the privacy consent native button transparent",
    );
    assert(
      /width:\s*auto;/.test(privacyButton) && /min-width:\s*0;/.test(privacyButton),
      files.wxss + " should prevent the privacy consent native button from stretching into a white block",
    );
  }
  assert(
    !(new RegExp(files.lightSelector).test(css)),
    files.wxss + " should not keep a light-mode override for the branded login screen",
  );
  assert(
    new RegExp('<view class="' + files.rootClass + '">').test(wxml),
    files.wxml + " should keep the login scene fixed to the dark branded surface",
  );
  assert(
    js.indexOf("helpers.isDark()") === -1,
    files.js + " should not switch the branded login page with the global theme",
  );
  assert(
    config.navigationStyle === "custom" && config.disableScroll === true,
    files.json + " should render the branded login surface under a custom nav",
  );
  if (files.rootClass === "manual-page") {
    assert(
      wxml.indexOf("🔐") === -1 && wxml.indexOf("🔑") === -1,
      files.wxml + " should keep the manual login form visually restrained",
    );
  }
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_login_button_visual_contract.js (" + pass + " assertions)");
