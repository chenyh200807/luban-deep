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

function loadAuthModule(filePath) {
  var source = fs.readFileSync(filePath, "utf8");
  var storage = {};
  var exported = null;
  var sandbox = {
    console: console,
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
      throw new Error("unexpected require");
    },
  };
  vm.runInNewContext(source, sandbox, { filename: filePath });
  exported = sandbox.module.exports;
  return { auth: exported, storage: storage };
}

function runSuite(label, relativePath) {
  var loaded = loadAuthModule(path.resolve(__dirname, "..", relativePath));
  var auth = loaded.auth;
  var storage = loaded.storage;

  var canonical = auth.selectUserId(
    { canonical_uid: "2d9eac15-5d26-4e93-941b-9ec6345ce6d9", id: "user_2008" },
    { user_id: "user_2008" }
  );
  assert(
    canonical === "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
    label + " should prefer canonical_uid over legacy ids"
  );

  auth.setToken("token-1", canonical);
  auth.setToken("token-2", "user_2008");
  assert(
    storage.auth_user_id === "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
    label + " should not downgrade stored uuid back to legacy user id"
  );

  var legacy = auth.selectUserId({ id: "user_2008" }, { user_id: "user_2008" });
  assert(legacy === "user_2008", label + " should preserve legacy id when no canonical uuid exists");
}

runSuite("yousen", "packageDeeptutor/utils/auth.js");
var wxAuthPath = path.resolve(__dirname, "..", "..", "wx_miniprogram/utils/auth.js");
var wxLoaded = loadAuthModule(wxAuthPath);
var wxAuth = wxLoaded.auth;
var wxStorage = wxLoaded.storage;

var wxCanonical = wxAuth.selectUserId(
  { canonical_uid: "2d9eac15-5d26-4e93-941b-9ec6345ce6d9", id: "user_2008" },
  { user_id: "user_2008" }
);
assert(wxCanonical === "2d9eac15-5d26-4e93-941b-9ec6345ce6d9", "wx should prefer canonical_uid over legacy ids");
wxAuth.setToken("token-1", wxCanonical);
wxAuth.setToken("token-2", "user_2008");
assert(
  wxStorage.auth_user_id === "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
  "wx should not downgrade stored uuid back to legacy user id"
);
assert(wxAuth.selectUserId({ id: "user_2008" }, { user_id: "user_2008" }) === "user_2008", "wx should preserve legacy id when no canonical uuid exists");

if (fail > 0) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS", pass);
