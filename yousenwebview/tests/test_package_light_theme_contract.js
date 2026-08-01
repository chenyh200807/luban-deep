// test_package_light_theme_contract.js - package light mode should stay token-driven and readable.
// Run: node yousenwebview/tests/test_package_light_theme_contract.js

var fs = require("fs");
var path = require("path");

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

function read(relativePath) {
  return fs.readFileSync(path.join(__dirname, "../packageDeeptutor", relativePath), "utf8");
}

var themeWxss = read("theme.wxss");
var chatWxss = read("pages/chat/chat.wxss");
var profileWxss = read("pages/profile/profile.wxss");
var billingWxss = read("pages/billing/billing.wxss");
var mistakeJs = read("pages/mistake-book/mistake-book.js");
var mistakeWxml = read("pages/mistake-book/mistake-book.wxml");
var mistakeWxss = read("pages/mistake-book/mistake-book.wxss");
var feedbackJs = read("pages/feedback/feedback.js");
var tabBarJs = read("custom-tab-bar/index.js");

assert(
  /page\.theme-light,\s*\.theme-light,\s*\.light\s*\{/.test(themeWxss),
  "subpackage theme should expose light tokens to root view .light classes",
);
assert(
  themeWxss.indexOf("--text-primary: #0f172a;") >= 0 &&
    themeWxss.indexOf("--text-muted: #64748b;") >= 0 &&
    themeWxss.indexOf("--accent-gold: #b45309;") >= 0,
  "light tokens should use accessible slate text and darker semantic accents",
);
assert(
  /\.page\.light\s+\.focus-label,\s*\.page\.light\s+\.focus-title\s*\{\s*color:\s*#b45309;/.test(chatWxss) &&
    /\.page\.light\s+\.focus-meta\s*\{[^}]*#8a4b05/.test(chatWxss),
  "chat light focus strip should not reuse low-contrast yellow text",
);
assert(
  /\.page\.light\s+\.callout-tag-conclusion\s*\{\s*color:\s*#92400e;\s*background:\s*#fef3c7;\s*border:\s*1rpx solid #fcd34d;\s*\}/.test(chatWxss) &&
    /\.page\.light\s+\.callout-tag-warning\s*\{\s*color:\s*#b91c1c;\s*background:\s*#fee2e2;\s*border:\s*1rpx solid #fca5a5;\s*\}/.test(chatWxss) &&
    /\.page\.light\s+\.callout-tag-highlight\s*\{\s*color:\s*#1d4ed8;\s*background:\s*#dbeafe;\s*border:\s*1rpx solid #93c5fd;\s*\}/.test(chatWxss) &&
    /\.page\.light\s+\.callout-tag-tip\s*\{\s*color:\s*#047857;\s*background:\s*#d1fae5;\s*border:\s*1rpx solid #6ee7b7;\s*\}/.test(chatWxss),
  "old-blue light callout tags should use fully opaque semantic colors instead of dark-mode alpha styles",
);
assert(
  !/\.page\.light\s+\.usage-meter-fill\s*\{\s*background:\s*#111827;/.test(chatWxss),
  "chat light usage meter should not render as a black bar",
);
assert(
  !/\.profile-page\.light\s+\.usage-meter-fill\s*\{\s*background:\s*#111827;/.test(profileWxss),
  "profile light usage meter should not render as a black bar",
);
assert(
  !/\.billing-page\.light\s+\.usage-meter-fill\s*\{[^}]*background:\s*#111827;/.test(billingWxss),
  "billing light usage meter should not render as a black bar",
);
assert(
  mistakeWxml.indexOf('class="mistake-book-page paper {{isDark?') >= 0 &&
    mistakeJs.indexOf('const helpers = require("../../utils/helpers");') >= 0 &&
    mistakeJs.indexOf('isDark: helpers.isDarkOr("light")') >= 0,
  "mistake-book should bind the root light class from the shared theme authority",
);
assert(
  /\.mistake-book-page\.light\s+\.mb-hero,[\s\S]*\.mistake-book-page\.light\s+\.mb-error\s*\{[\s\S]*background:\s*rgba\(255,\s*255,\s*255,\s*0\.96\)/.test(mistakeWxss) &&
    /\.mistake-book-page\.light\s+\.mistake-action\.danger\s*\{[\s\S]*color:\s*var\(--pk-warn\);/.test(mistakeWxss),
  "mistake-book should provide readable light surfaces and semantic danger actions",
);
assert(
  feedbackJs.indexOf('isDark: helpers.isDarkOr("light")') >= 0 &&
    feedbackJs.indexOf("onShow: function ()") >= 0,
  "feedback page should not force dark mode when light mode is selected",
);
assert(
  tabBarJs.indexOf('var hostRuntime = require("../utils/host-runtime");') >= 0 &&
    tabBarJs.indexOf('hostRuntime.getThemeOr("light") !== "light"') >= 0 &&
    tabBarJs.indexOf('typeof next.isDark !== "boolean"') >= 0,
  "custom tab bar should resolve light mode before page-level sync arrives",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_light_theme_contract.js (" + pass + " assertions)");
