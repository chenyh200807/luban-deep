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

function encodeBase64UrlJson(value) {
  return Buffer.from(JSON.stringify(value), "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function loadAuthModule(storage) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/auth.js"),
    "utf8",
  );
  var writes = [];
  var removes = [];
  var sandbox = {
    Buffer: Buffer,
    Date: {
      now: function () {
        return 1_700_000_000 * 1000;
      },
    },
    wx: {
      getStorageSync: function (key) {
        return storage[key] || "";
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
        writes.push({ key: key, value: value });
      },
      removeStorageSync: function (key) {
        delete storage[key];
        removes.push(key);
      },
    },
    module: { exports: {} },
    exports: {},
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/utils/auth.js",
  });

  return {
    auth: sandbox.module.exports,
    writes: writes,
    removes: removes,
  };
}

var stored = {};
var loaded = loadAuthModule(stored);

loaded.auth.setToken("fresh-token", 1_800_000_000);
assert(stored.auth_token === "fresh-token", "setToken should persist auth_token");
assert(stored.auth_token_exp === 1_800_000_000, "setToken should persist numeric auth_token_exp");
assert(loaded.auth.isLoggedIn() === true, "isLoggedIn should accept a non-expired token");

loaded.auth.clearToken();
assert(!("auth_token" in stored), "clearToken should remove auth_token");
assert(!("auth_token_exp" in stored), "clearToken should remove auth_token_exp");

var tokenPayload = encodeBase64UrlJson({ exp: 1_700_000_300 });
stored.auth_token = "dtm." + tokenPayload + ".signature";
var parsed = loaded.auth.getTokenExpiry();
assert(parsed === 1_700_000_300, "getTokenExpiry should fall back to parsing dtm token payload");
assert(
  loaded.auth.shouldRefreshToken(600) === true,
  "shouldRefreshToken should treat near-expiry token as refreshable",
);
stored.auth_token_exp = 1;
assert(loaded.auth.isLoggedIn() === false, "isLoggedIn should reject expired stored tokens");
assert(!("auth_token" in stored), "expired token should be cleared when checked");

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_auth_token_expiry.js (" + pass + " assertions)");
