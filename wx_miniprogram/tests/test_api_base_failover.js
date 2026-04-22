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
    path.join(__dirname, "../utils/api.js"),
    "utf8",
  );
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
    getApp: function () {
      return {
        globalData: {},
      };
    },
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
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        state.requests.push(options);
        if (state.requests.length === 1) {
          options.fail({ errMsg: "request:fail connect ECONNREFUSED 127.0.0.1:8001" });
          return;
        }
        options.success({
          statusCode: 200,
          data: { ok: true },
        });
      },
      reLaunch: function () {},
    },
    module: { exports: {} },
    exports: {},
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/utils/api.js",
  });

  return {
    api: sandbox.module.exports,
    state: state,
  };
}

(async function main() {
  var loaded = loadApiModule();
  var result = await loaded.api.request({
    url: "/api/v1/ping",
    method: "GET",
    noAuth: true,
  });
  await flushPromises();

  assert(
    loaded.state.requests.length === 2,
    "network failure on localhost should trigger one fallback request",
  );
  assert(
    loaded.state.requests[0].url === "http://127.0.0.1:8001/api/v1/ping",
    "first request should target localhost",
  );
  assert(
    loaded.state.requests[1].url === "https://test2.yousenjiaoyu.com/api/v1/ping",
    "second request should target the remote fallback host",
  );
  assert(
    loaded.state.remembered.length === 1 &&
      loaded.state.remembered[0].baseUrl === "https://test2.yousenjiaoyu.com" &&
      loaded.state.remembered[0].useGateway === false,
    "successful remote fallback should be remembered as the working API base",
  );
  assert(result && result.ok === true, "request should resolve with fallback response");

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_api_base_failover.js (" + pass + " assertions)");
})();
