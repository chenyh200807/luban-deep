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

var storage = { auth_token: "saved_token" };
var source = fs.readFileSync(
  path.join(__dirname, "../utils/auth.js"),
  "utf8",
);
var sandbox = {
  wx: {
    getStorageSync: function (key) {
      return storage[key] || "";
    },
    setStorageSync: function (key, value) {
      storage[key] = value;
    },
    removeStorageSync: function (key) {
      delete storage[key];
    },
  },
  module: { exports: {} },
  exports: {},
  require: function () {
    return {};
  },
};

vm.runInNewContext(source, sandbox, {
  filename: "utils/auth.js",
});

var moduleExports = sandbox.module.exports;
moduleExports.setToken("fresh_token", {
  canonical_uid: "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
  user_id: "user_2008",
});

assert(
  typeof moduleExports.extractUserIdFromAuthPayload === "undefined",
  "wx_miniprogram auth helper should no longer expose a local user_id extractor",
);

assert(
  moduleExports.getUserId() === "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
  "wx_miniprogram auth helper should persist canonical auth_user_id",
);

assert(
  storage.auth_token === "fresh_token",
  "wx_miniprogram auth helper should persist auth_token",
);

moduleExports.setToken("fresh_token_2", "user_2008");
assert(
  moduleExports.getUserId() === "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
  "wx_miniprogram auth helper should not downgrade uuid to legacy id",
);

assert(
  moduleExports.getToken() === "fresh_token_2",
  "wx_miniprogram auth helper should keep token reads unchanged",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_auth_user_id_resolution.js (" + pass + " assertions)");
