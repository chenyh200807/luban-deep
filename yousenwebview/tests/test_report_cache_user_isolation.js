// Run: node yousenwebview/tests/test_report_cache_user_isolation.js
var assert = require("assert");
var path = require("path");

var storage = {};
global.wx = {
  getStorageSync: function (key) { return storage[key]; },
  setStorageSync: function (key, value) { storage[key] = value; },
  removeStorageSync: function (key) { delete storage[key]; },
};

var modulePath = path.join(__dirname, "../packageDeeptutor/utils/report-cache.js");
delete require.cache[require.resolve(modulePath)];
var cache = require(modulePath);
var snapshotA = { report: { user_id: "student_a", overview: { focus_hint: "A 的弱点" } } };

assert.strictEqual(cache.write("student_a", snapshotA), true);
assert.deepStrictEqual(cache.read("student_a", 60 * 1000), snapshotA);
assert.strictEqual(cache.read("student_b", 60 * 1000), null, "B must never hydrate A's cache");
assert.strictEqual(cache.write("student_b", snapshotA), false, "mismatched report user must fail closed");
assert.strictEqual(cache.read("", 60 * 1000), null, "no canonical user means no cache hydration");

cache.clear("student_a");
assert.strictEqual(cache.read("student_a", 60 * 1000), null, "logout purge removes current user cache");

// All invalidation paths converge on auth.clearToken (logout, expiry, 401,
// forced login), so cache cleanup cannot depend on a specific page wrapper.
cache.write("student_a", snapshotA);
storage.auth_user_id = "student_a";
storage.auth_token = "token-a";
var authPath = path.join(__dirname, "../packageDeeptutor/utils/auth.js");
delete require.cache[require.resolve(authPath)];
var auth = require(authPath);
auth.clearToken();
assert.strictEqual(cache.read("student_a", 60 * 1000), null, "auth invalidation purges user report cache");
assert.strictEqual(storage.auth_user_id, undefined);

var reportPageSource = require("fs").readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
  "utf8",
);
assert.ok(reportPageSource.indexOf("_reportLoadGeneration") >= 0, "late report responses need a request generation guard");
assert.ok(reportPageSource.indexOf("currentUserId === userId") >= 0, "late responses must recheck the canonical user");
delete global.wx;
console.log("test_report_cache_user_isolation: all assertions passed");
