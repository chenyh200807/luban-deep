// test_profile_guest_exit.js — guest preview profile should expose an exit action.
// Run: node yousenwebview/tests/test_profile_guest_exit.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

function loadProfilePage() {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
    "utf8",
  );
  var pageDef = null;
  var logoutCalls = 0;
  var loginRedirectCalls = 0;
  var modalPayloads = [];
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          unwrapResponse: function (raw) {
            return raw;
          },
          getWallet: function () {
            return Promise.resolve({ balance: 0 });
          },
          getUsage: function () {
            return Promise.resolve({});
          },
          getLedger: function () {
            return Promise.resolve({ entries: [] });
          },
          getUserInfo: function () {
            return Promise.resolve({});
          },
          getBadges: function () {
            return Promise.resolve({ badges: [] });
          },
          updateSettings: function () {
            return Promise.resolve({});
          },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDark: function () {
            return true;
          },
          syncTabBar: function () {},
          vibrate: function () {},
        };
      }
      if (request === "../../utils/runtime") {
        return {
          getWorkspaceBack: function () {
            return null;
          },
          consumeWorkspaceBack: function () {
            return null;
          },
          setWorkspaceBack: function () {},
          markGoHome: function () {},
          redirectToLogin: function () {
            loginRedirectCalls++;
          },
          logout: function () {
            logoutCalls++;
          },
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
          feedback: function () {
            return "/packageDeeptutor/pages/feedback/feedback?source=profile";
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
        return {
          isLoggedIn: function () {
            return false;
          },
        };
      }
      if (request === "../../utils/learn-view-model") {
        // 纯函数视图模型（点亮判定单一权威），直接用真模块
        return require("../packageDeeptutor/utils/learn-view-model");
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () {
        return "";
      },
      showModal: function (payload) {
        modalPayloads.push(payload);
        payload.success({ confirm: true });
      },
      showToast: function () {},
      navigateTo: function () {},
      reLaunch: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/profile/profile.js",
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
    getLogoutCalls: function () {
      return logoutCalls;
    },
    getLoginRedirectCalls: function () {
      return loginRedirectCalls;
    },
    getModalPayloads: function () {
      return modalPayloads.slice();
    },
  };
}

var wxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/profile/profile.wxml"),
  "utf8",
);
assert(
  wxml.indexOf("{{isGuestPreview ? '退出体验' : '退出登录'}}") >= 0,
  "profile should render an exit label in guest preview",
);
assert(
  wxml.indexOf('wx:if="{{!isGuestPreview}}" bindtap="logout"') < 0,
  "profile should not hide logout from guest preview",
);

var loaded = loadProfilePage();
loaded.page.onLoad();
loaded.page.onShow();
assert(loaded.page.data.isGuestPreview === true, "profile should enter guest preview");
loaded.page.logout();

assert(loaded.getModalPayloads().length === 1, "guest exit should show one confirmation modal");
assert(
  loaded.getModalPayloads()[0].title === "退出体验",
  "guest exit confirmation should use exit-experience copy",
);
assert(loaded.getLogoutCalls() === 1, "guest exit should call runtime.logout");
assert(
  loaded.getLoginRedirectCalls() === 0,
  "guest exit should not route through quick-login redirect",
);

console.log("PASS test_profile_guest_exit.js");
