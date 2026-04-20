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

function loadApiModule(overrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/api.js"),
    "utf8",
  );
  var pendingRequests = [];
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
            return "token";
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
        return {
          redirectToLogin: function () {},
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        pendingRequests.push(options);
        if (typeof overrides.onRequest === "function") {
          overrides.onRequest(options);
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
    pendingRequests: pendingRequests,
  };
}

(async function main() {
  await run("state GET requests should dedupe concurrent in-flight reads", async function () {
    var loaded = loadApiModule({});
    var first = loaded.api.getWallet();
    var second = loaded.api.getWallet();

    assert(loaded.pendingRequests.length === 1, "concurrent wallet reads should collapse into a single wx.request");

    loaded.pendingRequests[0].success({
      statusCode: 200,
      data: { balance: 18 },
    });
    if (loaded.pendingRequests[1]) {
      loaded.pendingRequests[1].success({
        statusCode: 200,
        data: { balance: 18 },
      });
    }

    var result = await Promise.all([first, second]);
    assert(result[0].balance === 18, "deduped first wallet request should resolve with response data");
    assert(result[1].balance === 18, "deduped second wallet request should resolve with response data");
  });

  await run("state GET requests should not auto retry on 5xx", async function () {
    var requestCount = 0;
    var loaded = loadApiModule({
      onRequest: function (options) {
        requestCount += 1;
        options.success({
          statusCode: 500,
          data: { detail: "boom" },
        });
      },
    });

    var rejected = false;
    try {
      await loaded.api.getAssessmentProfile();
    } catch (_) {
      rejected = true;
    }
    await flushPromises();
    await flushPromises();

    assert(rejected === true, "assessment profile should still reject on 5xx");
    assert(requestCount === 1, "assessment profile should not schedule automatic retries after 5xx");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_api_request_dedupe.js (" + pass + " assertions)");
})();
