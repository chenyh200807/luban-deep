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
              "http://127.0.0.1:8012",
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
        if (typeof settings.requestHandler === "function") {
          settings.requestHandler(options, state);
          return;
        }
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
    loaded.state.requests[1].url === "http://127.0.0.1:8012/api/v1/ping",
    "second request should target the alternate local backend",
  );
  assert(
    loaded.state.remembered.length === 1 &&
      loaded.state.remembered[0].baseUrl === "http://127.0.0.1:8012" &&
      loaded.state.remembered[0].useGateway === false,
    "successful local fallback should be remembered as the working API base",
  );
  assert(result && result.ok === true, "request should resolve with fallback response");

  var postLoaded = loadApiModule({
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
        data: { token: "local-token" },
      });
    },
  });
  var postResult = await postLoaded.api.request({
    url: "/api/v1/auth/login",
    method: "POST",
    data: { username: "demo", password: "secret" },
    noAuth: true,
  });
  await flushPromises();

  assert(
    postLoaded.state.requests.length === 2,
    "local 503 on a POST should still trigger alternate local base fallback",
  );
  assert(
    postLoaded.state.requests[0].url === "http://127.0.0.1:8001/api/v1/auth/login",
    "POST fallback should first target localhost",
  );
  assert(
    postLoaded.state.requests[1].url === "http://127.0.0.1:8012/api/v1/auth/login",
    "POST fallback should retry the same login request on the alternate local host",
  );
  assert(
    postLoaded.state.remembered.length === 1 &&
      postLoaded.state.remembered[0].baseUrl === "http://127.0.0.1:8012",
    "successful local POST fallback should be remembered as the working API base",
  );
  assert(
    postResult && postResult.token === "local-token",
    "POST request should resolve with the fallback response",
  );

  var notFoundLoaded = loadApiModule({
    requestHandler: function (requestOptions) {
      requestOptions.success({
        statusCode: 404,
        data: { detail: "conversation not found" },
      });
    },
  });
  var notFoundError = null;
  try {
    await notFoundLoaded.api.request({
      url: "/api/v1/conversations/unified_missing/messages",
      method: "GET",
      noAuth: true,
    });
  } catch (err) {
    notFoundError = err;
  }
  await flushPromises();

  assert(
    notFoundLoaded.state.requests.length === 1,
    "HTTP 404 should not trigger base fallback",
  );
  assert(
    notFoundLoaded.state.requests[0].url ===
      "http://127.0.0.1:8001/api/v1/conversations/unified_missing/messages",
    "404 request should stay on the authoritative local base",
  );
  assert(
    notFoundLoaded.state.remembered.length === 0,
    "404 should not remember an alternate working base",
  );
  assert(
    notFoundError && notFoundError.statusCode === 404,
    "404 should be returned as the resource error",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_api_base_failover.js (" + pass + " assertions)");
})();
