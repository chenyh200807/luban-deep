// test_runtime_auth_return_to.js — auth redirect should preserve the current package target
// Run: node yousenwebview/tests/test_runtime_auth_return_to.js

var path = require("path");

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

var runtimePath = path.join(__dirname, "../packageDeeptutor/utils/runtime.js");
var authPath = path.join(__dirname, "../packageDeeptutor/utils/auth.js");
delete require.cache[require.resolve(runtimePath)];
delete require.cache[require.resolve(authPath)];

var reLaunchCalls = [];
global.wx = {
  getStorageSync: function () {
    return "";
  },
  removeStorageSync: function () {},
  reLaunch: function (options) {
    reLaunchCalls.push(options || {});
    if (options && typeof options.complete === "function") {
      options.complete();
    }
  },
  getNetworkType: function () {},
  onNetworkStatusChange: function () {},
};
global.getCurrentPages = function () {
  return [{ route: "packageDeeptutor/pages/report/report" }];
};
global.getApp = function () {
  return {
    globalData: {
      _authRedirecting: false,
    },
  };
};

var runtime = require(runtimePath);
var redirected = runtime.checkAuth(function () {});

assert(redirected === true, "checkAuth should start login redirect when token is missing");
assert(reLaunchCalls.length === 1, "checkAuth should relaunch to login once");
assert(
  reLaunchCalls[0].url ===
    "/packageDeeptutor/pages/login/login?returnTo=%2FpackageDeeptutor%2Fpages%2Freport%2Freport",
  "login redirect should preserve current package route as returnTo",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_runtime_auth_return_to.js (" + pass + " assertions)");
