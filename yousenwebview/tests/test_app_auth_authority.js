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

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

function loadApp(storageSeed) {
  var source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
  var storage = Object.assign({}, storageSeed || {});
  var readKeys = [];
  var removedKeys = [];
  var reLaunchCalls = [];
  var appDef = null;

  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: function () {
      return 1;
    },
    clearTimeout: function () {},
    require: function (request) {
      if (request === "./api/baseApi") {
        return {
          GetSysInfo: "Action=GetSysInfo",
        };
      }
      if (request === "./utils/config") {
        return {
          baseUrl: "https://xytk.kailly.com/Api/Xytk.ashx?",
        };
      }
      throw new Error("unexpected require: " + request);
    },
    __wxConfig: {
      envVersion: "develop",
      platform: "devtools",
    },
    getCurrentPages: function () {
      return [];
    },
    wx: {
      getStorageSync: function (key) {
        readKeys.push(key);
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      removeStorageSync: function (key) {
        removedKeys.push(key);
        delete storage[key];
      },
      reLaunch: function (options) {
        reLaunchCalls.push(options || {});
        if (options && typeof options.complete === "function") {
          options.complete();
        }
      },
      getWindowInfo: function () {
        return {
          statusBarHeight: 20,
        };
      },
      getSystemInfoSync: function () {
        return {};
      },
      onNetworkStatusChange: function () {},
      getNetworkType: function (options) {
        if (options && typeof options.success === "function") {
          options.success({ networkType: "wifi" });
        }
      },
      request: function (options) {
        if (options && typeof options.success === "function") {
          options.success({ data: { status: 1, data: {} } });
        }
      },
      showToast: function () {},
      navigateTo: function () {},
    },
    App: function (def) {
      appDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "app.js",
  });

  return {
    app: appDef,
    readKeys: readKeys,
    removedKeys: removedKeys,
    reLaunchCalls: reLaunchCalls,
  };
}

run("checkAuth should only trust auth_token and never read auth_user_id", function () {
  var setup = loadApp({
    auth_token: "",
    auth_user_id: "legacy_user_only",
  });
  var callbackToken = null;

  setup.app.checkAuth(function (token) {
    callbackToken = token;
  });

  assert(
    setup.readKeys.indexOf("auth_token") !== -1,
    "checkAuth should read auth_token",
  );
  assert(
    setup.readKeys.indexOf("auth_user_id") === -1,
    "checkAuth should not read legacy auth_user_id",
  );
  assert(
    callbackToken === null,
    "checkAuth should not authenticate from legacy auth_user_id alone",
  );
  assert(
    setup.reLaunchCalls.length === 1 &&
      setup.reLaunchCalls[0].url === "/packageDeeptutor/pages/login/login",
    "checkAuth should redirect to login when auth_token is missing",
  );
});

run("logout should clear legacy auth_user_id without ever reading it", function () {
  var setup = loadApp({
    auth_token: "token_1",
    auth_user_id: "legacy_user_1",
  });

  setup.app.logout();

  assert(
    setup.removedKeys.indexOf("auth_token") !== -1,
    "logout should clear auth_token",
  );
  assert(
    setup.removedKeys.indexOf("auth_user_id") !== -1,
    "logout should clear legacy auth_user_id",
  );
  assert(
    setup.readKeys.indexOf("auth_user_id") === -1,
    "logout should not read legacy auth_user_id before clearing it",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_app_auth_authority.js (" + pass + " assertions)");
