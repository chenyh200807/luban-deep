// test_profile_points_sync.js — profile points should stay aligned with wallet data

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

async function run(name, fn) {
  try {
    await fn();
  } catch (err) {
    fail++;
    errors.push(
      "ERROR: " + name + " -> " + (err && err.stack ? err.stack : err),
    );
  }
}

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

function loadProfilePage(overrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
    "utf8",
  );
  var pageDef = null;
  var apiMock = Object.assign(
    {
      unwrapResponse: function (raw) {
        if (
          raw &&
          typeof raw === "object" &&
          raw.data &&
          typeof raw.data === "object"
        ) {
          return raw.data;
        }
        return raw;
      },
      getUserInfo: function () {
        return Promise.resolve({ username: "chenyh2008", points: 0 });
      },
      getWallet: function () {
        return Promise.resolve({ balance: 88 });
      },
      getPoints: function () {
        return Promise.resolve({ points: 0 });
      },
      getUsage: function () {
        return Promise.resolve({ windows: [] });
      },
      getLedger: function () {
        return Promise.resolve({ entries: [] });
      },
      updateSettings: function () {
        return Promise.resolve({});
      },
    },
    (overrides && overrides.api) || {},
  );
  var helpersMock = {
    getWindowInfo: function () {
      return {
        statusBarHeight: 20,
      };
    },
    isDark: function () {
      return true;
    },
    syncTabBar: function () {},
    vibrate: function () {},
  };
  var runtimeMock = {
    getWorkspaceBack: function () {
      return null;
    },
    checkAuth: function (cb) {
      cb();
    },
    consumeWorkspaceBack: function () {
      return null;
    },
    markGoHome: function () {},
    setWorkspaceBack: function () {},
    logout: function () {},
  };
  var routeMock = {
    profile: function () {
      return "/packageDeeptutor/pages/profile/profile";
    },
    billing: function () {
      return "/packageDeeptutor/pages/billing/billing";
    },
    assessment: function () {
      return "/packageDeeptutor/pages/assessment/assessment";
    },
    report: function () {
      return "/packageDeeptutor/pages/report/report";
    },
    terms: function () {
      return "/packageDeeptutor/pages/legal/terms";
    },
    chat: function () {
      return "/packageDeeptutor/pages/chat/chat";
    },
  };
  var flagsMock = {
    getWorkspaceFlags: function () {
      return {};
    },
    ensureFeatureEnabled: function () {
      return true;
    },
    shouldShowWorkspaceShell: function () {
      return false;
    },
  };
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") return apiMock;
      // 2026-06-12 契约演进（paywall）：profile.js 新增 auth 依赖以支持游客态门控。
      // 测试场景均为已登录用户，isLoggedIn 返回 true。
      if (request === "../../utils/auth") {
        return {
          isLoggedIn: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/helpers") return helpersMock;
      if (request === "../../utils/runtime") return runtimeMock;
      if (request === "../../utils/route") return routeMock;
      if (request === "../../utils/flags") return flagsMock;
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
      navigateTo: function () {},
      reLaunch: function () {},
      showToast: function () {},
      showModal: function () {},
      chooseMedia: function () {},
      getFileSystemManager: function () {
        return { saveFile: function () {} };
      },
      setStorageSync: function () {},
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
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  return { page: page };
}

(async function main() {
  await run(
    "profile should hydrate usage quota from profile-owned usage API",
    async function () {
      var loaded = loadProfilePage({
        api: {
          getUserInfo: function () {
            return Promise.resolve({ username: "chenyh2008" });
          },
          getUsage: function () {
            return Promise.resolve({
              display: { primary_label: "剩余 88%", primary_percent: 88, reference_points: 100 },
              rows: [{ key: "weekly", remaining_percent: 88 }],
            });
          },
          getWallet: function () {
            return Promise.resolve({
              balance: 88,
              plan_id: "vip",
              entitlement: { reference_points: 100 },
            });
          },
          getLedger: function () {
            return Promise.resolve({
              entries: [{ delta: 100 }],
            });
          },
        },
      });

      loaded.page.onLoad();
      loaded.page.onShow();
      await flushPromises();
      await flushPromises();

      assert(
        loaded.page.data.usageRows.some(function (row) {
          return row.key === "wallet_percent";
        }),
        "profile should render wallet usage rows",
      );
      assert(
        loaded.page.data.usagePrimaryLabel === "剩余 88%",
        "profile should hydrate primary usage quota",
      );
      var walletRow = loaded.page.data.usageRows.find(function (row) {
        return row.key === "wallet_percent";
      });
      assert(
        walletRow && walletRow.remainingLabel === "剩余 88%",
        "profile usage detail should expose remaining label for the sheet",
      );
      assert(
        walletRow && walletRow.barStyle === "width:88%",
        "profile usage detail should expose deterministic progress width",
      );
    },
  );

  await run(
    "profile should degrade usage quota without touching legacy points APIs",
    async function () {
      var legacyPointsCalls = 0;
      var loaded = loadProfilePage({
        api: {
          getUserInfo: function () {
            return Promise.resolve({ username: "chenyh2008" });
          },
          getWallet: function () {
            return Promise.resolve({ balance: 144 });
          },
          getPoints: function () {
            legacyPointsCalls += 1;
            return Promise.resolve({ points: 52 });
          },
          getUsage: function () {
            return Promise.reject(new Error("usage unavailable"));
          },
        },
      });

      loaded.page.onLoad();
      loaded.page.onShow();
      await flushPromises();
      await flushPromises();

      assert(
        legacyPointsCalls === 0,
        "profile should not read legacy point balances",
      );
      assert(
        loaded.page.data.usageRows.length === 1,
        "profile should still render wallet usage when usage fallback fails",
      );
      assert(
        loaded.page.data.usageLoading === false,
        "profile should stop usage loading on usage failure",
      );
    },
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_profile_points_sync.js (" + pass + " assertions)");
})();
