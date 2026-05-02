// test_route_authority.js — package route resolver must not pass host/unknown paths through
// Run: node yousenwebview/tests/test_route_authority.js

var path = require("path");

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

var routePath = path.join(__dirname, "../packageDeeptutor/utils/route.js");
delete require.cache[require.resolve(routePath)];
var route = require(routePath);
var fallback = "/packageDeeptutor/pages/chat/chat";

assert(
  route.resolveInternalUrl("/packageDeeptutor/pages/report/report?from=profile", fallback) ===
    "/packageDeeptutor/pages/report/report?from=profile",
  "package report returnTo should be preserved",
);
assert(
  route.resolveInternalUrl("/pages/report/report?from=profile", fallback) ===
    "/packageDeeptutor/pages/report/report?from=profile",
  "known deeptutor main-page alias should be normalized into package route",
);
assert(
  route.resolveInternalUrl("/pages/freeCourse/freeCourse", fallback) === fallback,
  "host home returnTo should not be passed through as package login target",
);
assert(
  route.resolveInternalUrl("/packageDeeptutor/pages/unknown/unknown", fallback) === fallback,
  "unknown package returnTo should fallback instead of causing a 404 route",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_route_authority.js (" + pass + " assertions)");
