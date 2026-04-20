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

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

function loadApiModule() {
  var source = fs.readFileSync(
    path.join(__dirname, "../utils/api.js"),
    "utf8",
  );
  var clearCount = 0;
  var relaunchCount = 0;
  var requestOptions = null;
  var sandbox = {
    console: {
      warn: function () {},
      log: function () {},
      error: console.error,
    },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Promise: Promise,
    getApp: function () {
      return {
        globalData: {},
      };
    },
    require: function (request) {
      if (request === "./auth") {
        return {
          getToken: function () {
            return "token";
          },
          clearToken: function () {
            clearCount++;
          },
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
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        requestOptions = options;
      },
      reLaunch: function () {
        relaunchCount++;
      },
    },
    module: { exports: {} },
    exports: {},
  };

  vm.runInNewContext(source, sandbox, {
    filename: "utils/api.js",
  });

  return {
    api: sandbox.module.exports,
    getRequestOptions: function () {
      return requestOptions;
    },
    getClearCount: function () {
      return clearCount;
    },
    getRelaunchCount: function () {
      return relaunchCount;
    },
  };
}

(async function main() {
  var loaded = loadApiModule();
  var rejectedMessage = "";

  loaded.api
    .request({
      url: "/api/v1/auth/login",
      method: "POST",
      data: { username: "demo", password: "wrong" },
      noAuth: true,
    })
    .catch(function (err) {
      rejectedMessage = String((err && err.message) || "");
    });

  loaded.getRequestOptions().success({
    statusCode: 401,
    data: { detail: "用户名或密码错误" },
  });
  await flushPromises();
  await flushPromises();

  assert(
    rejectedMessage.indexOf("HTTP_401") === 0,
    "noAuth requests should reject with HTTP_401 instead of pretending auth expired",
  );
  assert(
    loaded.getClearCount() === 0,
    "noAuth 401 should not clear the stored token",
  );
  assert(
    loaded.getRelaunchCount() === 0,
    "noAuth 401 should not relaunch the login page",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_api_noauth_401.js (" + pass + " assertions)");
})();
