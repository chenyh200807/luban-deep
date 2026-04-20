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

var writes = [];
var removes = [];
var source = fs.readFileSync(
  path.join(__dirname, "../utils/auth.js"),
  "utf8",
);
var sandbox = {
  wx: {
    getStorageSync: function (key) {
      return key === "auth_token" ? "saved_token" : "";
    },
    setStorageSync: function (key, value) {
      writes.push({ key: key, value: value });
    },
    removeStorageSync: function (key) {
      removes.push(key);
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
moduleExports.setToken("fresh_token", "ignored_user_id");

assert(
  typeof moduleExports.extractUserIdFromAuthPayload === "undefined",
  "wx_miniprogram auth helper should no longer expose a local user_id extractor",
);

assert(
  typeof moduleExports.getUserId === "undefined",
  "wx_miniprogram auth helper should no longer expose local auth_user_id reads",
);

assert(
  writes.length === 1 &&
    writes[0].key === "auth_token" &&
    writes[0].value === "fresh_token",
  "wx_miniprogram auth helper should only persist auth_token",
);

assert(
  removes.indexOf("auth_user_id") !== -1,
  "wx_miniprogram auth helper should clear legacy auth_user_id cache when setting token",
);

assert(
  moduleExports.getToken() === "saved_token",
  "wx_miniprogram auth helper should keep token reads unchanged",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_auth_user_id_resolution.js (" + pass + " assertions)");
