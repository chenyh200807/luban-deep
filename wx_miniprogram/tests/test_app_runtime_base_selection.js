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
    __USE_LOCAL_DIRECT__: settings.useLocalDirect,
    __NGROK_URL__: settings.ngrokUrl,
    __PROD_API__: settings.prodApi,
    __PROD_GATEWAY__: settings.prodGateway,
    require: function (request) {
      if (request === "./utils/auth") {
        return {
          getToken: function () {
            return "";
          },
          clearToken: function () {},
        };
      }
      if (request === "./utils/endpoints") {
        return {
          getBaseUrlCandidates: function (_useGateway, preferredBase) {
            var list = [];
            if (preferredBase) list.push(preferredBase);
            list.push("http://127.0.0.1:8001");
            list.push("http://127.0.0.1:8012");
            return list;
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      showModal: function () {},
      onNetworkStatusChange: function () {},
      getNetworkType: function (opts) {
        if (opts && typeof opts.success === "function") {
          opts.success({ networkType: "wifi" });
        }
      },
      showToast: function () {},
      getStorageSync: function () {
        return "";
      },
      setStorageSync: function () {},
      reLaunch: function () {},
    },
    App: function (config) {
      appConfig = config;
    },
    getCurrentPages: function () {
      return [];
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/app.js",
  });

  return appConfig;
}

(function main() {
  var defaultDevtools = loadAppModule({
    wxConfig: { envVersion: "develop", platform: "devtools" },
  });
  assert(!!defaultDevtools, "App config should be registered");
  assert(
    defaultDevtools.globalData.apiUrl === "http://127.0.0.1:8001",
    "develop devtools should default to localhost API first",
  );
  assert(
    defaultDevtools.globalData.gatewayUrl === "http://127.0.0.1:8001",
    "develop devtools should default to localhost gateway first",
  );
  assert(
    Array.isArray(defaultDevtools.globalData.apiCandidates) &&
      defaultDevtools.globalData.apiCandidates[0] === "http://127.0.0.1:8001" &&
      defaultDevtools.globalData.apiCandidates.indexOf("https://test2.yousenjiaoyu.com") >= 0,
    "develop devtools runtime candidates should keep localhost first and remote fallback",
  );

  var explicitLocal = loadAppModule({
    wxConfig: { envVersion: "develop", platform: "devtools" },
    useLocalDirect: true,
  });
  assert(
    explicitLocal.globalData.apiUrl === "http://127.0.0.1:8001",
    "explicit local direct flag should keep localhost API",
  );
  assert(
    explicitLocal.globalData.apiCandidates[0] === "http://127.0.0.1:8001" &&
      explicitLocal.globalData.apiCandidates.indexOf("https://test2.yousenjiaoyu.com") >= 0,
    "explicit local direct flag should retain localhost-first candidate list with remote fallback",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_app_runtime_base_selection.js (" + pass + " assertions)");
})();
