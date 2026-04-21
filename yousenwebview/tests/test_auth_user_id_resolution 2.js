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

var source = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/utils/auth.js"),
  "utf8",
);
var moduleExports = null;
var sandbox = {
  wx: {
    getStorageSync: function () {
      return "";
    },
    setStorageSync: function () {},
    removeStorageSync: function () {},
  },
  module: { exports: {} },
  exports: {},
  require: function () {
    return {};
  },
};

vm.runInNewContext(source, sandbox, {
  filename: "packageDeeptutor/utils/auth.js",
});
moduleExports = sandbox.module.exports;

assert(
  moduleExports.extractUserIdFromAuthPayload({
    user_id: "top_level_uid",
    user: { id: "legacy_id" },
  }) === "top_level_uid",
  "auth payload helper should prefer the canonical top-level user_id over legacy id fields",
);

assert(
  moduleExports.extractUserIdFromAuthPayload({
    data: {
      user: { user_id: "nested_uid", id: "legacy_nested_id" },
    },
  }) === "nested_uid",
  "auth payload helper should read nested user.user_id from wrapped API responses",
);

assert(
  moduleExports.extractUserIdFromAuthPayload({
    data: {
      id: "legacy_only_id",
    },
  }) === "legacy_only_id",
  "auth payload helper should still fall back to legacy id fields for backward compatibility",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_auth_user_id_resolution.js (" + pass + " assertions)");
