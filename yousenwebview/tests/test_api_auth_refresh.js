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
    path.join(__dirname, "../packageDeeptutor/utils/api.js"),
    "utf8",
  );
  var state = {
    token: config.initialToken || "",
    expiry: config.initialExpiry || 0,
    setTokenCalls: [],
    clearTokenCalls: 0,
    redirectCalls: 0,
    requests: [],
  };
  var sandbox = {
    console: {
      warn: function () {},
      log: console.log,
      error: console.error,
    },
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Promise: Promise,
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
      if (request === "./runtime") {
        return {
          redirectToLogin: function () {
            state.redirectCalls += 1;
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        state.requests.push(options);
        config.onRequest(options, state);
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
  await run("protected request should silently refresh near-expiry token once", async function () {
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
          data: { balance: 18 },
        });
      },
    });

    var result = await loaded.api.getWallet();

    assert(loaded.state.requests.length === 2, "wallet request should trigger refresh then replay once");
    assert(
      loaded.state.requests[0].url === "https://api.example.com/api/v1/auth/refresh",
      "first request should be auth refresh",
    );
    assert(
      loaded.state.requests[1].header.Authorization === "Bearer new-token",
      "replayed request should carry refreshed bearer token",
    );
    assert(
      loaded.state.setTokenCalls.length === 1 &&
        loaded.state.setTokenCalls[0].token === "new-token" &&
        loaded.state.setTokenCalls[0].expiresAt === 1_800_000_000,
      "refresh should persist the new token and expiry",
    );
    assert(result.balance === 18, "replayed wallet request should resolve normally");
  });

  await run("gateway auth request should refresh against the same gateway origin", async function () {
    var loaded = loadApiModule({
      initialToken: "old-token",
      initialExpiry: 1,
      shouldRefreshToken: true,
      onRequest: function (options) {
        if (options.url === "https://gateway.example.com/api/v1/auth/refresh") {
          options.success({
            statusCode: 200,
            data: {
              token: "gateway-token",
              expires_at: 1_800_000_100,
            },
          });
          return;
        }
        options.success({
          statusCode: 200,
          data: { ok: true },
        });
      },
    });

    var result = await loaded.api.bindPhone("phone-code");

    assert(loaded.state.requests.length === 2, "gateway request should also refresh then replay once");
    assert(
      loaded.state.requests[0].url === "https://gateway.example.com/api/v1/auth/refresh",
      "gateway refresh should stay on the gateway origin",
    );
    assert(
      loaded.state.requests[1].url === "https://gateway.example.com/api/v1/wechat/mp/bind-phone",
      "business request should replay on the same gateway origin",
    );
    assert(
      loaded.state.requests[1].header.Authorization === "Bearer gateway-token",
      "gateway replay should use refreshed token",
    );
    assert(result.ok === true, "gateway request should still resolve normally");
  });

  await run("refresh failure should clear token and redirect without replaying business request", async function () {
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
      await loaded.api.getWallet();
    } catch (err) {
      rejected = err && err.message === "AUTH_EXPIRED";
    }
    await flushPromises();

    assert(rejected === true, "wallet request should reject with AUTH_EXPIRED when refresh fails");
    assert(loaded.state.requests.length === 1, "business request should not be sent after failed refresh");
    assert(loaded.state.clearTokenCalls === 1, "failed refresh should clear stored token once");
    assert(loaded.state.redirectCalls === 1, "failed refresh should redirect to login once");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_api_auth_refresh.js (" + pass + " assertions)");
})();
