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

function encodeBase64UrlJson(payload) {
  return Buffer.from(JSON.stringify(payload), "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function loadAuthModule(stored) {
  var source = fs.readFileSync(
    path.join(__dirname, "../utils/auth.js"),
    "utf8",
  );
  var sandbox = {
    Buffer: Buffer,
    wx: {
      getStorageSync: function (key) {
        return Object.prototype.hasOwnProperty.call(stored, key) ? stored[key] : "";
      },
      setStorageSync: function (key, value) {
        stored[key] = value;
      },
      removeStorageSync: function (key) {
        delete stored[key];
      },
    },
    module: { exports: {} },
    exports: {},
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/utils/auth.js",
  });

  return sandbox.module.exports;
}

(function main() {
  var stored = {};
  var auth = loadAuthModule(stored);

  auth.setToken("fresh-token", 1_800_000_000);
  assert(stored.auth_token === "fresh-token", "setToken should persist auth_token");
  assert(stored.auth_token_exp === 1_800_000_000, "setToken should persist numeric auth_token_exp");

  auth.clearToken();
  assert(!("auth_token" in stored), "clearToken should remove auth_token");
  assert(!("auth_token_exp" in stored), "clearToken should remove auth_token_exp");

  var tokenPayload = encodeBase64UrlJson({ exp: 1_700_000_300 });
  stored.auth_token = "dtm." + tokenPayload + ".signature";
  var parsed = auth.getTokenExpiry();
  assert(parsed === 1_700_000_300, "getTokenExpiry should parse dtm token payload fallback");
  assert(
    auth.shouldRefreshToken(60 * 60 * 24 * 365) === true,
    "shouldRefreshToken should treat near-expiry token as refreshable",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_auth_token_expiry.js (" + pass + " assertions)");
})();
