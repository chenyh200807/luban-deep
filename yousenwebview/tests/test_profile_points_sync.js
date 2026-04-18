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
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
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
        if (raw && typeof raw === "object" && raw.data && typeof raw.data === "object") {
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
      if (request === "../../utils/helpers") return helpersMock;
      if (request === "../../utils/runtime") return runtimeMock;
      if (request === "../../utils/route") return routeMock;
      if (request === "../../utils/flags") return flagsMock;
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
  await run("profile should update displayed points from wallet balance", async function () {
    var loaded = loadProfilePage({
      api: {
        getUserInfo: function () {
          return Promise.resolve({ username: "chenyh2008", points: 0 });
        },
        getWallet: function () {
          return Promise.resolve({ balance: 144 });
        },
      },
    });

    loaded.page.onLoad();
    loaded.page.onShow();
    await flushPromises();
    await flushPromises();

    assert(loaded.page.data.points === 144, "profile points should sync from wallet balance");
    assert(loaded.page.data.userPoints === 144, "profile userPoints should stay aligned with points");
  });

  await run("profile should fallback to points api when wallet is unavailable", async function () {
    var loaded = loadProfilePage({
      api: {
        getUserInfo: function () {
          return Promise.resolve({ username: "chenyh2008", points: 0 });
        },
        getWallet: function () {
          return Promise.reject(new Error("wallet unavailable"));
        },
        getPoints: function () {
          return Promise.resolve({ points: 52 });
        },
      },
    });

    loaded.page.onLoad();
    loaded.page.onShow();
    await flushPromises();
    await flushPromises();

    assert(loaded.page.data.points === 52, "profile should fallback to legacy points api");
    assert(loaded.page.data.userPoints === 52, "profile fallback should keep both point fields aligned");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_profile_points_sync.js (" + pass + " assertions)");
})();
