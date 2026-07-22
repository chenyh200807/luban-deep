// Production WeChat channel-attribution contract.
// y ousenwebview is the DevTools project root; packageDeeptutor is the target
// subpackage. The production client must forward the same channel/scene wire
// fields accepted by the mobile router.
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

function loadApiModule(storageState, capture) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/api.js"),
    "utf8",
  );
  var sandbox = {
    console: { warn: function () {}, log: function () {}, error: console.error },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Promise: Promise,
    getApp: function () {
      return { globalData: {} };
    },
    require: function (request) {
      if (request === "./auth") {
        return {
          getToken: function () {
            return "";
          },
          clearToken: function () {},
        };
      }
      if (request === "./endpoints") {
        return {
          getPrimaryBaseUrl: function () {
            return "https://api.example.com";
          },
          getBaseUrlCandidates: function () {
            return ["https://api.example.com"];
          },
          rememberWorkingBaseUrl: function () {},
        };
      }
      if (request === "./runtime") {
        return { redirectToLogin: function () {} };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return storageState[key];
      },
      setStorageSync: function (key, value) {
        storageState[key] = value;
      },
      request: function (options) {
        capture.options = options;
      },
      reLaunch: function () {},
    },
    module: { exports: {} },
    exports: {},
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "packageDeeptutor/utils/api.js" });
  return sandbox.module.exports;
}

function loadAppForAttribution(storageState) {
  var source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
  var appConfig = null;
  var sandbox = {
    console: { info: function () {}, warn: function () {}, error: function () {} },
    __wxConfig: { envVersion: "release", platform: "ios" },
    require: function (request) {
      if (request === "./api/baseApi") return { GetSysInfo: "/sys" };
      if (request === "./utils/config") return { baseUrl: "https://host.example.com" };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) { return storageState[key]; },
      setStorageSync: function (key, value) { storageState[key] = value; },
      removeStorageSync: function (key) { delete storageState[key]; },
    },
    App: function (config) { appConfig = config; },
    getCurrentPages: function () { return []; },
    setTimeout: function () {},
    clearTimeout: function () {},
  };
  vm.runInNewContext(source, sandbox, { filename: "yousenwebview/app.js" });
  return appConfig;
}

(function testProductionApiCarriesChannelAttribution() {
  var storage = { reg_attribution: { ch: "campaign_7", scene: "1047" } };
  var capture = {};
  var api = loadApiModule(storage, capture);

  api.wxLoginWithPhone("wx-code", "phone-code-123");
  var loginData = capture.options && capture.options.data;
  assert(loginData.channel === "campaign_7", "login body carries channel");
  assert(loginData.scene === "1047", "login body carries scene");

  api.bindPhone("phone-code-456");
  var bindData = capture.options && capture.options.data;
  assert(bindData.channel === "campaign_7", "bind body carries channel");
  assert(bindData.scene === "1047", "bind body carries scene");
})();

(function testExplicitUnlimitedCodeSceneCarriesCampaignWithoutConfusingLaunchScene() {
  var encodedStorage = {};
  var encodedApp = loadAppForAttribution(encodedStorage);
  encodedApp._captureChannelAttribution({
    scene: 1047,
    query: { scene: "ch%3Dcampaign_9%26landing%3Dlearn" },
  });
  assert(
    encodedStorage.reg_attribution.ch === "campaign_9",
    "explicit ch token in encoded query.scene becomes campaign channel",
  );
  assert(
    encodedStorage.reg_attribution.scene === "1047",
    "numeric launch scene remains the WeChat entry scenario",
  );

  var numericStorage = {};
  var numericApp = loadAppForAttribution(numericStorage);
  numericApp._captureChannelAttribution({ scene: 1005, query: { scene: "1005" } });
  assert(
    numericStorage.reg_attribution.ch === "",
    "numeric scene never masquerades as a campaign channel",
  );
})();

(function testProductionEntryAndRegisterAreWired() {
  var appSource = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
  var registerSource = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/register/register.js"),
    "utf8",
  );
  assert(
    appSource.indexOf("_captureChannelAttribution") >= 0 &&
      appSource.indexOf("reg_attribution") >= 0,
    "project root captures launch attribution",
  );
  assert(
    registerSource.indexOf("api.regAttribution()") >= 0 &&
      registerSource.indexOf("channel: attribution.channel") >= 0 &&
      registerSource.indexOf("scene: attribution.scene") >= 0,
    "production password registration forwards attribution",
  );
})();

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_channel_attribution_transmission.js (" + pass + " assertions)");
