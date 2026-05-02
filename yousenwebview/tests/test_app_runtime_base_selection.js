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

function loadAppModule(options) {
  var source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
  var appConfig = null;
  var settings = options || {};
  var storage = {};
  var sandbox = {
    console: {
      info: function () {},
      warn: function () {},
      error: function () {},
    },
    __wxConfig: settings.wxConfig || {
      envVersion: "develop",
      platform: "devtools",
    },
    __USE_LOCAL_DEVTOOLS__: settings.useLocalDevtools,
    __NGROK_URL__: settings.ngrokUrl,
    __PROD_API__: settings.prodApi,
    __PROD_GATEWAY__: settings.prodGateway,
    require: function (request) {
      if (request === "./api/baseApi") return { GetSysInfo: "/sys" };
      if (request === "./utils/config") return { baseUrl: "https://host.example.com" };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      login: function (opts) {
        if (opts && typeof opts.success === "function") opts.success({});
      },
      showModal: function () {},
      onNetworkStatusChange: function () {},
      getNetworkType: function (opts) {
        if (opts && typeof opts.success === "function") {
          opts.success({ networkType: "wifi" });
        }
      },
      showToast: function () {},
      getStorageSync: function (key) {
        return storage[key] || "";
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      removeStorageSync: function (key) {
        delete storage[key];
      },
      reLaunch: function () {},
    },
    App: function (config) {
      appConfig = config;
    },
    getCurrentPages: function () {
      return [];
    },
    setTimeout: function () {},
    clearTimeout: function () {},
  };

  vm.runInNewContext(source, sandbox, {
    filename: "yousenwebview/app.js",
  });
  appConfig.onLaunch.call(appConfig);
  return appConfig;
}

(function main() {
  var defaultDevtools = loadAppModule({
    wxConfig: { envVersion: "develop", platform: "devtools" },
  });
  assert(!!defaultDevtools, "App config should be registered");
  assert(
    defaultDevtools.globalData.apiUrl === "https://test2.yousenjiaoyu.com",
    "develop devtools should keep the configured remote API by default",
  );
  assert(
    defaultDevtools.globalData.gatewayUrl === "https://test2.yousenjiaoyu.com",
    "develop devtools should keep the configured remote gateway by default",
  );
  assert(
    Array.isArray(defaultDevtools.globalData.apiCandidates) &&
      defaultDevtools.globalData.apiCandidates.length === 1 &&
      defaultDevtools.globalData.apiCandidates[0] === "https://test2.yousenjiaoyu.com",
    "develop devtools should not append localhost candidates by default",
  );

  var explicitLocal = loadAppModule({
    wxConfig: { envVersion: "develop", platform: "devtools" },
    useLocalDevtools: true,
  });
  assert(
    explicitLocal.globalData.apiUrl === "http://127.0.0.1:8001",
    "explicit local-devtools true should use localhost API",
  );
  assert(
    explicitLocal.globalData.apiCandidates.length === 1 &&
      explicitLocal.globalData.apiCandidates[0] === "http://127.0.0.1:8001",
    "explicit local mode should use only the configured localhost candidate",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_app_runtime_base_selection.js (" + pass + " assertions)");
})();
