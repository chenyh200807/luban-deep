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

async function run(name, fn) {
  try {
    await fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
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
    token: config.initialToken || "",
    expiry: config.initialExpiry || 0,
    setTokenCalls: [],
    clearTokenCalls: 0,
    relaunchCalls: 0,
    requests: [],
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
            return state.token;
          },
          setToken: function (token, expiresAt) {
            state.token = token;
            state.expiry = expiresAt || 0;
            state.setTokenCalls.push({ token: token, expiresAt: expiresAt || 0 });
          },
          clearToken: function () {
            state.clearTokenCalls += 1;
            state.token = "";
            state.expiry = 0;
          },
          shouldRefreshToken: function () {
            return !!state.token && !!config.shouldRefreshToken;
          },
        };
      }
      if (request === "./endpoints") {
        return {
          getPrimaryBaseUrl: function () {
            return "https://api.example.com";
          },
          getBaseUrlCandidates: function (useGateway) {
            if (useGateway) {
              return ["https://gateway.example.com"];
            }
            return ["https://api.example.com"];
          },
          rememberWorkingBaseUrl: function () {},
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        state.requests.push(options);
        config.onRequest(options, state);
      },
      reLaunch: function () {
        state.relaunchCalls += 1;
      },
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
  await run("createConversation should refresh near-expiry token before sending protected POST", async function () {
    var loaded = loadApiModule({
      initialToken: "old-token",
      initialExpiry: 1,
      shouldRefreshToken: true,
      onRequest: function (options) {
        if (options.url === "https://api.example.com/api/v1/auth/refresh") {
          options.success({
            statusCode: 200,
            data: {
              token: "new-token",
              expires_at: 1_800_000_000,
            },
          });
          return;
        }
        options.success({
          statusCode: 200,
          data: { id: "conv-1" },
        });
      },
    });

    var result = await loaded.api.createConversation();

    assert(loaded.state.requests.length === 2, "createConversation should trigger refresh then replay once");
    assert(
      loaded.state.requests[0].url === "https://api.example.com/api/v1/auth/refresh",
      "first request should be auth refresh",
    );
    assert(
      loaded.state.requests[1].url === "https://api.example.com/api/v1/conversations",
      "second request should be the actual createConversation call",
    );
    assert(
      loaded.state.requests[1].header.Authorization === "Bearer new-token",
      "createConversation should use refreshed bearer token",
    );
    assert(
      loaded.state.setTokenCalls.length === 1 &&
        loaded.state.setTokenCalls[0].token === "new-token" &&
        loaded.state.setTokenCalls[0].expiresAt === 1_800_000_000,
      "refresh should persist the new token and expiry",
    );
    assert(result.id === "conv-1", "createConversation should resolve normally after refresh");
  });

  await run("refresh failure should clear token and relaunch login without sending protected request", async function () {
    var loaded = loadApiModule({
      initialToken: "expired-token",
      initialExpiry: 1,
      shouldRefreshToken: true,
      onRequest: function (options) {
        options.success({
          statusCode: 401,
          data: { detail: "expired" },
        });
      },
    });

    var rejected = false;
    try {
      await loaded.api.createConversation();
    } catch (err) {
      rejected = err && err.message === "AUTH_EXPIRED";
    }
    await flushPromises();

    assert(rejected === true, "createConversation should reject with AUTH_EXPIRED when refresh fails");
    assert(loaded.state.requests.length === 1, "business request should not be sent after failed refresh");
    assert(loaded.state.clearTokenCalls === 1, "failed refresh should clear stored token once");
    assert(loaded.state.relaunchCalls === 1, "failed refresh should relaunch login once");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_api_auth_refresh.js (" + pass + " assertions)");
})();
