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
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/api.js"),
    "utf8",
  );
  var settings = config || {};
  var state = {
    requests: [],
    remembered: [],
  };
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
            return "";
          },
        };
      }
      if (request === "./endpoints") {
        return {
          getPrimaryBaseUrl: function () {
            return "http://127.0.0.1:8001";
          },
          getBaseUrlCandidates: function () {
            return [
              "http://127.0.0.1:8001",
              "https://test2.yousenjiaoyu.com",
            ];
          },
          rememberWorkingBaseUrl: function (baseUrl, useGateway) {
            state.remembered.push({ baseUrl: baseUrl, useGateway: !!useGateway });
          },
        };
      }
      if (request === "./runtime") {
        return {
          redirectToLogin: function () {},
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        state.requests.push(options);
        if (typeof settings.requestHandler === "function") {
          settings.requestHandler(options, state);
          return;
        }
        options.success({
          statusCode: 200,
          data: { ok: true },
        });
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
    state: state,
  };
}

(async function main() {
  var loaded = loadApiModule({
    requestHandler: function (requestOptions, state) {
      if (state.requests.length === 1) {
        requestOptions.success({
          statusCode: 503,
          data: { detail: "local service unavailable" },
        });
        return;
      }
      requestOptions.success({
        statusCode: 200,
        data: { token: "remote-token" },
      });
    },
  });
  var result = await loaded.api.request({
    url: "/api/v1/auth/login",
    method: "POST",
    data: { username: "demo", password: "secret" },
    noAuth: true,
  });
  await flushPromises();

  assert(
    loaded.state.requests.length === 2,
    "local 503 on a POST should trigger remote base fallback",
  );
  assert(
    loaded.state.requests[0].url === "http://127.0.0.1:8001/api/v1/auth/login",
    "first POST should target localhost",
  );
  assert(
    loaded.state.requests[1].url === "https://test2.yousenjiaoyu.com/api/v1/auth/login",
    "second POST should target the remote fallback host",
  );
  assert(
    loaded.state.remembered.length === 1 &&
      loaded.state.remembered[0].baseUrl === "https://test2.yousenjiaoyu.com" &&
      loaded.state.remembered[0].useGateway === false,
    "successful remote fallback should be remembered as the working API base",
  );
  assert(result && result.token === "remote-token", "request should resolve with fallback response");

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_api_base_failover.js (" + pass + " assertions)");
})();
