// Run: node yousenwebview/tests/test_retest_completion_authority.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var retest = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.js"),
  "utf8",
);
var handoff = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/handoff/handoff.js"),
  "utf8",
);
var review = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/review/review.js"),
  "utf8",
);
var gauntlet = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/gauntlet/gauntlet.js"),
  "utf8",
);
var errorbank = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/errorbank/errorbank.js"),
  "utf8",
);

assert.ok(retest.indexOf("completeLubanRetest") >= 0, "retest must use canonical completion endpoint");
assert.strictEqual(retest.indexOf("postStationCompleted"), -1, "retest page must not be a second station writer");
assert.strictEqual(handoff.indexOf("postStationCompleted"), -1, "handoff must be presentation-only");
assert.ok(retest.indexOf('syncStatus: "synced"') >= 0, "receipt must be gated by durable sync");
assert.ok(retest.indexOf("probe_id: this.data.probeId") >= 0, "review must preserve canonical probe identity");
assert.ok(retest.indexOf("selection_id: this.data.selectionId") >= 0, "completion must preserve server-issued selection identity");
assert.ok(review.indexOf("entry.probeId") >= 0, "review due entry must forward probe identity");
assert.ok(gauntlet.indexOf('"&mode=forward"') >= 0, "gauntlet repeat must be forward practice");
assert.ok(errorbank.indexOf("getLubanReviewDue") >= 0, "errorbank must consume canonical review due");
assert.strictEqual(errorbank.indexOf("getLubanRetestItems"), -1, "errorbank must not infer due from supply");
assert.ok(errorbank.indexOf('"&mode=review&probe_id="') >= 0, "errorbank must forward due probe");

console.log("PASS test_retest_completion_authority.js");
