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
  var updateSettingsCalls = [];
  var storageValue = (overrides && overrides.storageValue) || "";
  var apiMock = Object.assign(
    {
      unwrapResponse: function (raw) {
        if (raw && typeof raw === "object" && raw.data && typeof raw.data === "object") {
          return raw.data;
        }
        return raw;
      },
      getUserInfo: function () {
        return Promise.resolve({
          username: "chenyh2008",
          avatar_url: "https://server.example/avatar.png",
        });
      },
      getWallet: function () {
        return Promise.resolve({ balance: 0 });
      },
      getPoints: function () {
        return Promise.resolve({ points: 0 });
      },
      updateSettings: function (patch) {
        updateSettingsCalls.push(patch);
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
  var chooseMediaHandler = (overrides && overrides.chooseMedia) || function (opts) {
    opts.success({
      tempFiles: [
        {
          tempFilePath: "/tmp/new-avatar.png",
          size: 128 * 1024,
        },
      ],
    });
  };
  var saveFileHandler = (overrides && overrides.saveFile) || function (opts) {
    opts.success({ savedFilePath: "/local/saved-avatar.png" });
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
      getStorageSync: function (key) {
        if (key === "local_avatar_path") return storageValue;
        return "";
      },
      setStorageSync: function (key, value) {
        if (key === "local_avatar_path") storageValue = value;
      },
      chooseMedia: chooseMediaHandler,
      getFileSystemManager: function () {
        return { saveFile: saveFileHandler };
      },
      showToast: function () {},
      showModal: function () {},
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
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  return {
    page: page,
    apiMock: apiMock,
    getUpdateSettingsCalls: function () {
      return updateSettingsCalls.slice();
    },
    getStorageValue: function () {
      return storageValue;
    },
  };
}

(async function main() {
  await run("local avatar cache should take precedence over server avatar_url", async function () {
    var loaded = loadProfilePage({
      storageValue: "/local/cached-avatar.png",
      api: {
        getUserInfo: function () {
          return Promise.resolve({
            username: "chenyh2008",
            avatar_url: "https://server.example/avatar.png",
          });
        },
      },
    });

    loaded.page.onLoad();
    loaded.page.onShow();
    await flushPromises();
    await flushPromises();

    assert(
      loaded.page.data.avatarUrl === "/local/cached-avatar.png",
      "profile should keep local cached avatar on device UI",
    );
  });

  await run("avatar selection should not write local file path into profile settings", async function () {
    var loaded = loadProfilePage();

    loaded.page.onLoad();
    loaded.page.onChangeAvatar();
    await flushPromises();
    await flushPromises();

    assert(
      loaded.page.data.avatarUrl === "/local/saved-avatar.png",
      "profile should show the saved local avatar path immediately",
    );
    assert(
      loaded.getStorageValue() === "/local/saved-avatar.png",
      "local avatar path should be persisted only in device storage",
    );
    assert(
      loaded.getUpdateSettingsCalls().length === 0,
      "avatar selection should not call updateSettings",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_profile_avatar_authority.js (" + pass + " assertions)");
})();
