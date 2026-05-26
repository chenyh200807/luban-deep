// test_profile_feedback_entry_contract.js — profile feedback should use DeepTutor feedback pipeline
// Run: node wx_miniprogram/tests/test_profile_feedback_entry_contract.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var profileJs = fs.readFileSync(
  path.join(__dirname, "../pages/profile/profile.js"),
  "utf8",
);
var profileWxml = fs.readFileSync(
  path.join(__dirname, "../pages/profile/profile.wxml"),
  "utf8",
);
var profileWxss = fs.readFileSync(
  path.join(__dirname, "../pages/profile/profile.wxss"),
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
    getApp: function () {
      return {
        globalData: {},
        checkAuth: function (cb) {
          cb();
        },
      };
    },
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          submitFeedback: submitFeedback,
          updateSettings: function () {
            return Promise.resolve({});
          },
        };
      }
      if (request === "../../utils/auth") return {};
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
      switchTab: function () {},
      getStorageSync: function () {
        return "";
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };
  vm.runInNewContext(profileJs, sandbox, {
    filename: "wx_miniprogram/pages/profile/profile.js",
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
  return { page: page, toasts: toasts, modals: modals, navigations: navigations };
}

assert(
  /id:\s*["']feedback["'][\s\S]*title:\s*["']意见反馈["']/.test(profileJs) &&
    profileJs.indexOf("nativeOpenType") < 0,
  "profile feedback item should be a first-party row, not native WeChat feedback",
);
assert(
  profileWxml.indexOf('bindtap="openLink"') >= 0 &&
    profileWxml.indexOf('open-type="{{item.nativeOpenType}}"') < 0 &&
    profileWxml.indexOf("link-row-button") < 0,
  "profile feedback row should use the same left-aligned link-row layout as other rows",
);
assert(
  profileWxss.indexOf(".link-row-button") < 0,
  "profile should not keep native button styles that shift feedback alignment",
);
assert(
  profileJs.indexOf("openFeedbackPage") >= 0 &&
    profileJs.indexOf("/pages/feedback/feedback") >= 0,
  "profile feedback should navigate to the dedicated feedback page",
);

(async function run() {
  var calls = [];
  var loaded = loadProfilePage(function (payload) {
    calls.push(payload);
    return Promise.resolve({ ok: true });
  });
  loaded.page.openLink({ currentTarget: { dataset: { id: "feedback" } } });
  await flush();

  assert(loaded.modals.length === 0, "feedback row should not open the old editable modal");
  assert(calls.length === 0, "profile row should not submit feedback before the dedicated page form");
  assert(loaded.navigations.length === 1, "feedback row should navigate once");
  assert(
    loaded.navigations[0].url === "/pages/feedback/feedback?source=profile",
    "feedback row should open the dedicated feedback page with a source hint",
  );
  console.log("PASS test_profile_feedback_entry_contract.js");
})();
