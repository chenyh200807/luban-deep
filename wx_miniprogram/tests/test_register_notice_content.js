// test_register_notice_content.js — register pages should expose clear user notice disclaimers.
// Run: node wx_miniprogram/tests/test_register_notice_content.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

function loadRegisterPage(filePath, filename, options) {
  var source = fs.readFileSync(filePath, "utf8");
  var pageDef = null;
  var sandbox = {
    console: console,
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          request: function () {
            return Promise.resolve({ token: "token" });
          },
          describeRequestError: function (_err, fallbackMsg) {
            return fallbackMsg;
          },
        };
      }
      if (request === "../../utils/auth") {
        return {
          isLoggedIn: function () {
            return false;
          },
          setToken: function () {},
        };
      }
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20, screenHeight: 812, safeArea: { bottom: 778 } };
          },
          isDark: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/route") {
        return {
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
          login: function () {
            return "/packageDeeptutor/pages/login/login";
          },
          resolveInternalUrl: function (_value, fallback) {
            return fallback;
          },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      navigateTo: function (payload) {
        sandbox.__lastNavigateTo = payload;
      },
      navigateBack: function () {},
      redirectTo: function () {},
      reLaunch: function () {},
      switchTab: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, { filename: filename });
  return { data: pageDef && pageDef.data, pageDef: pageDef, sandbox: sandbox };
}

var wxPage = loadRegisterPage(
  path.join(__dirname, "../pages/register/register.js"),
  "wx_miniprogram/pages/register/register.js",
);
var packagePage = loadRegisterPage(
  path.join(
    __dirname,
    "../../yousenwebview/packageDeeptutor/pages/register/register.js",
  ),
  "yousenwebview/packageDeeptutor/pages/register/register.js",
);
var wxWxml = fs.readFileSync(
  path.join(__dirname, "../pages/register/register.wxml"),
  "utf8",
);
var packageWxml = fs.readFileSync(
  path.join(
    __dirname,
    "../../yousenwebview/packageDeeptutor/pages/register/register.wxml",
  ),
  "utf8",
);
var wxWxss = fs.readFileSync(
  path.join(__dirname, "../pages/register/register.wxss"),
  "utf8",
);
var packageWxss = fs.readFileSync(
  path.join(
    __dirname,
    "../../yousenwebview/packageDeeptutor/pages/register/register.wxss",
  ),
  "utf8",
);

assert(wxPage.data, "wx register page should register data");
assert(packagePage.data, "package register page should register data");
assert(
  JSON.stringify(packagePage.data.registerNoticeItems) ===
    JSON.stringify(wxPage.data.registerNoticeItems),
  "package register notice should match wx register notice",
);
assert(
  wxPage.data.registerNoticeItems.length >= 8,
  "register notice should include enough risk disclosures",
);

var allText = wxPage.data.registerNoticeItems.join("\n");
[
  "不承诺通过考试",
  "不等同于考试机构",
  "最新官方发布",
  "自行核验",
  "工程实践判断",
  "上传、输入或传播",
  "未成年人",
  "第三方接口",
  "不可抗力",
  "实际支付的费用",
  "消费者权益",
].forEach(function (keyword) {
  assert(allText.indexOf(keyword) >= 0, "register notice should include " + keyword);
});

[
  [wxWxml, "wx wxml"],
  [packageWxml, "package wxml"],
].forEach(function (pair) {
  assert(pair[0].indexOf("用户须知") >= 0, pair[1] + " should render notice title");
  assert(
    pair[0].indexOf("registerNoticeItems") >= 0,
    pair[1] + " should render notice items from data",
  );
  assert(pair[0].indexOf("bindtap=\"openTerms\"") >= 0, pair[1] + " should link terms");
});

[
  [wxWxss, "wx wxss"],
  [packageWxss, "package wxss"],
].forEach(function (pair) {
  assert(pair[0].indexOf(".notice-panel") >= 0, pair[1] + " should style notice panel");
  assert(
    pair[0].indexOf(".scene.light .notice-panel") >= 0,
    pair[1] + " should support light mode notice panel",
  );
});

wxPage.pageDef.openTerms.call({});
packagePage.pageDef.openTerms.call({});
assert(
  wxPage.sandbox.__lastNavigateTo.url === "/pages/legal/terms",
  "wx register notice should open root terms page",
);
assert(
  packagePage.sandbox.__lastNavigateTo.url === "/packageDeeptutor/pages/legal/terms",
  "package register notice should open package terms page",
);

console.log("PASS test_register_notice_content.js");
