// test_package_profile_badges_authority.js — package profile should read /profile/badges
// Run: node yousenwebview/tests/test_package_profile_badges_authority.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

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

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function loadProfilePage(apiOverrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
    "utf8",
  );
  var pageDef = null;
  var getBadgesCalls = 0;
  var api = Object.assign({
    unwrapResponse: function (raw) { return raw; },
    getUserInfo: function () { return Promise.resolve({ username: "chenyh2008", earned_badge_ids: [2] }); },
    getWallet: function () { return Promise.resolve({ balance: 0 }); },
    getPoints: function () { return Promise.resolve({ points: 0 }); },
    getBadges: function () {
      getBadgesCalls += 1;
      return Promise.resolve({
        badges: [
          { id: 1, icon: "A", name: "服务端首徽章", earned: true },
          { id: 2, icon: "B", name: "服务端次徽章", earned: false },
        ],
      });
    },
    updateSettings: function () { return Promise.resolve({}); },
  }, apiOverrides || {});
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    wx: {
      getStorageSync: function () { return ""; },
      setStorageSync: function () {},
      getFileSystemManager: function () { return { saveFile: function () {} }; },
      chooseMedia: function () {},
      showToast: function () {},
      showModal: function () {},
      navigateTo: function () {},
      reLaunch: function () {},
    },
    require: function (request) {
      if (request === "../../utils/api") return api;
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () { return { statusBarHeight: 20 }; },
          isDark: function () { return true; },
          syncTabBar: function () {},
          vibrate: function () {},
        };
      }
      if (request === "../../utils/runtime") {
        return {
          getWorkspaceBack: function () { return null; },
          checkAuth: function (cb) { cb(); },
          consumeWorkspaceBack: function () { return null; },
          setWorkspaceBack: function () {},
          markGoHome: function () {},
          logout: function () {},
        };
      }
      if (request === "../../utils/route") {
        return {
          profile: function () { return "/packageDeeptutor/pages/profile/profile"; },
          billing: function () { return "/packageDeeptutor/pages/billing/billing"; },
          assessment: function () { return "/packageDeeptutor/pages/assessment/assessment"; },
          report: function () { return "/packageDeeptutor/pages/report/report"; },
          terms: function () { return "/packageDeeptutor/pages/legal/terms"; },
          chat: function () { return "/packageDeeptutor/pages/chat/chat"; },
        };
      }
      if (request === "../../utils/flags") {
        return {
          getWorkspaceFlags: function () { return {}; },
          ensureFeatureEnabled: function () { return true; },
          shouldShowWorkspaceShell: function () { return false; },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    Page: function (def) { pageDef = def; },
  };
  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/profile/profile.js",
  });
  var page = {
    data: Object.assign({}, pageDef.data),
    setData: function (patch) { this.data = Object.assign({}, this.data, patch || {}); },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, getBadgesCalls: function () { return getBadgesCalls; } };
}

(async function main() {
  var loaded = loadProfilePage();
  loaded.page.onLoad();
  loaded.page.onShow();
  await flush();
  await flush();

  assert(loaded.getBadgesCalls() === 1, "package profile should call canonical badge api");
  assert(loaded.page.data.badges[0].name === "服务端首徽章", "package profile should use server badge catalog");
  assert(loaded.page.data.badges[0].earned === true, "package profile should use server earned state");
  assert(loaded.page.data.badges[0].desc.indexOf("首次") >= 0, "package profile should enrich badge description");

  var fallback = loadProfilePage({
    getBadges: function () { return Promise.reject(new Error("badges unavailable")); },
  });
  fallback.page.onLoad();
  fallback.page.onShow();
  await flush();
  await flush();

  assert(fallback.page.data.badges[1].earned === true, "package profile should fallback to earned_badge_ids");

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_package_profile_badges_authority.js (" + pass + " assertions)");
})().catch(function (err) {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
