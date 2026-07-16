// test_package_profile_feedback_entry_contract.js — package profile feedback should use DeepTutor feedback pipeline
// Run: node yousenwebview/tests/test_package_profile_feedback_entry_contract.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var profileJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
  "utf8",
);
var profileWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/profile/profile.wxml"),
  "utf8",
);
var profileWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/profile/profile.wxss"),
  "utf8",
);

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

function flush() {
  return Promise.resolve().then(function () {
    return Promise.resolve();
  });
}

function loadProfilePage(submitFeedback) {
  var pageDef = null;
  var toasts = [];
  var modals = [];
  var navigations = [];
  var sandbox = {
    console: console,
    Set: Set,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          submitFeedback: submitFeedback,
          updateSettings: function () {
            return Promise.resolve({});
          },
          unwrapResponse: function (raw) {
            return raw;
          },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          vibrate: function () {},
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDark: function () {
            return true;
          },
          syncTabBar: function () {},
        };
      }
      if (request === "../../utils/runtime") {
        return {
          checkAuth: function (cb) {
            cb();
          },
          getWorkspaceBack: function () {
            return null;
          },
          setWorkspaceBack: function () {},
          markGoHome: function () {},
          logout: function () {},
        };
      }
      if (request === "../../utils/route") {
        return {
          profile: function () {
            return "/packageDeeptutor/pages/profile/profile";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
          assessment: function () {
            return "/packageDeeptutor/pages/assessment/assessment";
          },
          report: function () {
            return "/packageDeeptutor/pages/report/report";
          },
          billing: function () {
            return "/packageDeeptutor/pages/billing/billing";
          },
          feedback: function (query) {
            var suffix = query && query.source ? "?source=" + query.source : "";
            return "/packageDeeptutor/pages/feedback/feedback" + suffix;
          },
          terms: function () {
            return "/packageDeeptutor/pages/legal/terms";
          },
        };
      }
      if (request === "../../utils/flags") {
        return {
          getWorkspaceFlags: function () {
            return {};
          },
          ensureFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/auth") {
        // 2026-06-12 契约演进（paywall）：profile.js 新增 auth 依赖以支持游客态门控。
        // 测试场景均为已登录用户，isLoggedIn 返回 true。
        return {
          isLoggedIn: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/learn-view-model") {
        // 纯函数视图模型（点亮判定单一权威），直接用真模块
        return require("../packageDeeptutor/utils/learn-view-model");
      }
      if (request === "../../utils/surface-telemetry") {
        return { trackModuleView: function () {}, trackModuleExit: function () {} };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      showModal: function (payload) {
        modals.push(payload);
        payload.success({ confirm: true, content: "  意见反馈入口排版不齐  " });
      },
      showToast: function (payload) {
        toasts.push(payload);
      },
      navigateTo: function (payload) {
        navigations.push(payload);
      },
      reLaunch: function () {},
      getStorageSync: function () {
        return "";
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };
  vm.runInNewContext(profileJs, sandbox, {
    filename: "yousenwebview/packageDeeptutor/pages/profile/profile.js",
  });
  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return {
    page: page,
    toasts: toasts,
    modals: modals,
    navigations: navigations,
  };
}

assert(
  /id:\s*["']feedback["'],\s*title:\s*["']客服与反馈["']/.test(profileJs) &&
    profileJs.indexOf("nativeOpenType") < 0,
  "package profile feedback item should be a first-party row, not native WeChat feedback",
);
assert(
  profileWxml.indexOf('bindtap="openLink"') >= 0 &&
    profileWxml.indexOf('open-type="{{item.nativeOpenType}}"') < 0 &&
    profileWxml.indexOf("link-row-button") < 0,
  "package profile feedback row should use the same left-aligned link-row layout as other rows",
);
assert(
  profileWxss.indexOf(".link-row-button") < 0,
  "package profile should not keep native button styles that shift feedback alignment",
);
assert(
  profileJs.indexOf("openFeedbackPage") >= 0 &&
    profileJs.indexOf("route.feedback") >= 0,
  "package profile feedback should navigate to the dedicated feedback page",
);

(async function run() {
  var calls = [];
  var loaded = loadProfilePage(function (payload) {
    calls.push(payload);
    return Promise.resolve({ ok: true });
  });
  loaded.page.openLink({ currentTarget: { dataset: { id: "feedback" } } });
  await flush();

  assert(
    loaded.modals.length === 0,
    "package feedback row should not open the old editable modal",
  );
  assert(
    calls.length === 0,
    "package profile row should not submit feedback before the dedicated page form",
  );
  assert(
    loaded.navigations.length === 1,
    "package feedback row should navigate once",
  );
  assert(
    loaded.navigations[0].url ===
      "/packageDeeptutor/pages/feedback/feedback?source=profile",
    "package feedback row should open the dedicated feedback page with a source hint",
  );
  console.log("PASS test_package_profile_feedback_entry_contract.js");
})();
