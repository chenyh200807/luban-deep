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

function loadApiModule(config) {
  var settings = config || {};
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/api.js"),
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
      if (request === "./runtime") {
        return {
          redirectToLogin: function () {
            relaunchCount++;
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        requestOptions = options;
        if (typeof settings.requestHandler === "function") {
          settings.requestHandler(options);
        }
      },
    },
    module: { exports: {} },
    exports: {},
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/utils/api.js",
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
    rejectedMessage.indexOf("用户名或密码错误") === -1 && rejectedMessage.indexOf("detail") === -1,
    "noAuth 401 should not expose raw backend response payload",
  );
  assert(
    loaded.getClearCount() === 0,
    "noAuth 401 should not clear the stored token",
  );
  assert(
    loaded.getRelaunchCount() === 0,
    "noAuth 401 should not relaunch the login page",
  );

  var unavailableLoaded = loadApiModule({
    requestHandler: function (options) {
      options.success({
        statusCode: 503,
        data: { detail: "短信服务未配置，生产环境已禁止调试验证码" },
      });
    },
  });
  var unavailableMessage = "";
  var unavailableStatus = 0;
  unavailableLoaded.api
    .request({
      url: "/api/v1/auth/send-code",
      method: "POST",
      data: { phone: "13800000000" },
      noAuth: true,
    })
    .catch(function (err) {
      unavailableMessage = String((err && err.message) || "");
      unavailableStatus = err && err.statusCode;
    });
  await flushPromises();
  await flushPromises();

  assert(
    unavailableStatus === 503,
    "noAuth 503 should preserve the HTTP status for UI error mapping",
  );
  assert(
    unavailableMessage.indexOf("短信服务未配置") >= 0,
    "noAuth 503 should preserve backend detail instead of opaque FEATURE_DISABLED",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_api_noauth_401.js (" + pass + " assertions)");
})();
