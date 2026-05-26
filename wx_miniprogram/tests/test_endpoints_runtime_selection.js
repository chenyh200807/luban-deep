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

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
    pass++;
    return;
  }
  fail++;
  errors.push(
    "FAIL: " +
      message +
      "\n  expected: " +
      JSON.stringify(expected) +
      "\n  actual:   " +
      JSON.stringify(actual),
  );
}

function loadEndpointsModule(options) {
  var source = fs.readFileSync(
    path.join(__dirname, "../utils/endpoints.js"),
    "utf8",
  );
  var config = options || {};
  var appState = {
    globalData: {
      gatewayUrl: "",
      apiUrl: "",
      gatewayCandidates: [],
      apiCandidates: [],
    },
  };
  if (config.runtimeBaseConfig) {
    appState.globalData.gatewayUrl = config.runtimeBaseConfig.primary || "";
    appState.globalData.apiUrl = config.runtimeBaseConfig.primary || "";
    appState.globalData.gatewayCandidates = (config.runtimeBaseConfig.candidates || []).slice();
    appState.globalData.apiCandidates = (config.runtimeBaseConfig.candidates || []).slice();
  }
  var sandbox = {
    __wxConfig: config.wxConfig || { envVersion: "develop" },
    getApp: function () {
      return appState;
    },
    require: function (request) {
      if (request === "./host-runtime") {
        return {
          getRuntimeBaseConfig: function (useGateway) {
            var primaryKey = useGateway ? "gatewayUrl" : "apiUrl";
            var candidatesKey = useGateway
              ? "gatewayCandidates"
              : "apiCandidates";
            return {
              primary: String(appState.globalData[primaryKey] || "").trim(),
              candidates: Array.isArray(appState.globalData[candidatesKey])
                ? appState.globalData[candidatesKey].slice()
                : [],
            };
          },
          rememberWorkingBaseUrl: function (baseUrl, useGateway) {
            var primaryKey = useGateway ? "gatewayUrl" : "apiUrl";
            var candidatesKey = useGateway
              ? "gatewayCandidates"
              : "apiCandidates";
            var normalized = String(baseUrl || "").trim();
            if (!normalized) return;
            appState.globalData[primaryKey] = normalized;
            var candidates = Array.isArray(appState.globalData[candidatesKey])
              ? appState.globalData[candidatesKey].slice()
              : [];
            appState.globalData[candidatesKey] = [normalized]
              .concat(candidates)
              .filter(function (item, index, list) {
                return item && list.indexOf(item) === index;
              });
          },
        };
      }
      throw new Error("Unexpected require: " + request);
    },
    module: { exports: {} },
    exports: {},
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/utils/endpoints.js",
  });

  return {
    endpoints: sandbox.module.exports,
    appState: appState,
  };
}

(function main() {
  var releaseLoaded = loadEndpointsModule({
    wxConfig: { envVersion: "release" },
    runtimeBaseConfig: { primary: "", candidates: [] },
  });
  assertEqual(
    releaseLoaded.endpoints.getBaseUrlCandidates(false),
    ["https://test2.yousenjiaoyu.com"],
    "release mode without runtime config should fall back to remote base",
  );
  assert(
    releaseLoaded.endpoints.getPrimaryBaseUrl(false) === "https://test2.yousenjiaoyu.com",
    "release mode primary base should be the production host",
  );

  var remoteRuntimeLoaded = loadEndpointsModule({
    wxConfig: { envVersion: "develop" },
    runtimeBaseConfig: {
      primary: "http://127.0.0.1:8001",
      candidates: [
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8012",
        "https://test2.yousenjiaoyu.com",
      ],
    },
  });
  assertEqual(
    remoteRuntimeLoaded.endpoints.getBaseUrlCandidates(false),
    [
      "http://127.0.0.1:8001",
      "http://127.0.0.1:8012",
      "https://test2.yousenjiaoyu.com",
    ],
    "runtime-configured candidates should stay localhost first with remote fallback and no extra reordering",
  );

  remoteRuntimeLoaded.endpoints.rememberWorkingBaseUrl("https://test2.yousenjiaoyu.com", false);
  assert(
    remoteRuntimeLoaded.appState.globalData.apiUrl === "https://test2.yousenjiaoyu.com",
    "rememberWorkingBaseUrl should persist into app globalData",
  );
  assertEqual(
    remoteRuntimeLoaded.endpoints.getBaseUrlCandidates(false),
    [
      "https://test2.yousenjiaoyu.com",
      "http://127.0.0.1:8001",
      "http://127.0.0.1:8012",
    ],
    "after a successful remote fallback, remote should become the remembered primary without inventing extra candidates",
  );

  var strictRemoteRuntimeLoaded = loadEndpointsModule({
    wxConfig: { envVersion: "develop" },
    runtimeBaseConfig: {
      primary: "https://test2.yousenjiaoyu.com",
      candidates: [],
    },
  });
  assertEqual(
    strictRemoteRuntimeLoaded.endpoints.getBaseUrlCandidates(false),
    ["https://test2.yousenjiaoyu.com"],
    "when runtime already declares remote-only, endpoints should not invent localhost candidates in develop mode",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_endpoints_runtime_selection.js (" + pass + " assertions)");
})();
