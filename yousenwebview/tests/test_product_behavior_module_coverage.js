// Run: node yousenwebview/tests/test_product_behavior_module_coverage.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var packageRoot = path.join(__dirname, "../packageDeeptutor");
var telemetryPath = path.join(packageRoot, "utils/surface-telemetry.js");
var authPath = path.join(packageRoot, "utils/auth.js");
var endpointsPath = path.join(packageRoot, "utils/endpoints.js");
var requests = [];
var storage = {};

require.cache[require.resolve(authPath)] = {
  exports: {
    getToken: function () { return "qa-token"; },
    getUserId: function () { return "qa_eval_product_behavior"; },
  },
};
require.cache[require.resolve(endpointsPath)] = {
  exports: { getPrimaryBaseUrl: function () { return "https://example.invalid"; } },
};
global.wx = {
  getStorageSync: function (key) { return storage[key]; },
  setStorageSync: function (key, value) { storage[key] = value; },
  request: function (payload) {
    requests.push(payload.data);
    if (payload.success) payload.success({ data: { accepted: true, status: "accepted" } });
  },
};

delete require.cache[require.resolve(telemetryPath)];
var telemetry = require(telemetryPath);
var page = {};
telemetry.trackModuleView(page, { module: "history", section: "home" });
telemetry.trackModuleView(page, { module: "history", section: "home" });
telemetry.trackModuleExit(page);
telemetry.trackModuleExit(page);

assert.deepStrictEqual(
  requests.map(function (request) { return request.event_name; }),
  ["module_viewed", "module_exited"],
  "one page visibility interval must emit one view and one exit",
);
assert.strictEqual(requests[0].metadata.module, "history");
assert.strictEqual(requests[1].metadata.action, "return");
assert(requests[1].metadata.duration_ms >= 0);
telemetry.trackProductBehavior("learning_action_completed", {
  module: "first_run",
  action: "complete",
  objectType: "script",
  result: "synced",
  eventVersion: 2,
});
assert.strictEqual(requests[2].metadata.event_version, 2, "event version must reach server metadata");

var requiredPages = {
  "pages/learn/learn.js": "learning",
  "pages/chat/chat.js": "chat",
  "pages/history/history.js": "history",
  "pages/report/report.js": "learning_report",
  "pages/profile/profile.js": "profile",
  "pages/practice/practice.js": "practice",
  "pages/assessment/assessment.js": "assessment",
  "pages/mistake-book/mistake-book.js": "notebook",
};
Object.keys(requiredPages).forEach(function (relativePath) {
  var source = fs.readFileSync(path.join(packageRoot, relativePath), "utf8");
  assert(source.indexOf("trackModuleView") >= 0, relativePath + " must emit module_viewed");
  assert(source.indexOf("trackModuleExit") >= 0, relativePath + " must emit module_exited");
  assert(source.indexOf('module: "' + requiredPages[relativePath] + '"') >= 0, relativePath + " module drift");
});

console.log("PASS test_product_behavior_module_coverage.js");
