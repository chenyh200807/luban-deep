// Run: node yousenwebview/tests/test_retest_bridge_decode.js
//
// Behavioral test for the H5→小程序 bridge receipt decode fallback.
//
// QA death evidence: the compiled practice HTML injector encodeURIComponent()s the
// answers/projection_receipt payloads into the retest jump URL
// (deeptutor/services/luban_lesson/practice_html.py:733). DevTools measured the wx
// redirect path delivering the query STILL percent-encoded (`answers` ~790 chars
// starting `%5B%7B%22`), so a naïve JSON.parse throws → parseBridgeReceipt returns
// null → the user is told "题目内容已更新，请返回重新完成五题". Real-device web-view JSSDK
// may auto-decode once, so the parser must succeed under BOTH encoded and
// already-decoded inputs, and must be idempotent (double-encoded `%25...` too).
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

// Load the real retest.js in an isolated sandbox and expose the module-scoped
// parseBridgeReceipt so we exercise the shipped function (not a copy).
var src = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.js"),
  "utf8",
);
var harness = src + "\n;module.exports.__parseBridgeReceipt = parseBridgeReceipt;\n";
var sandbox = { module: { exports: {} }, require: function () { return {}; }, Page: function () {}, console: console };
sandbox.exports = sandbox.module.exports;
vm.runInNewContext(harness, sandbox, { filename: "retest.js" });
var parseBridgeReceipt = sandbox.module.exports.__parseBridgeReceipt;
assert.strictEqual(typeof parseBridgeReceipt, "function", "parseBridgeReceipt must be reachable for behavioral test");

// Canonical five-answer payload (variant/option ids are hyphenated alnum — never a literal '%').
var CANONICAL_ANSWERS = [
  { variant_id: "F16-html-q1-a", selected_option_id: "F16-html-q1-a-opt2" },
  { variant_id: "F16-html-q2-b", selected_option_id: "F16-html-q2-b-opt1" },
  { variant_id: "F16-html-q3-c", selected_option_id: "F16-html-q3-c-opt3" },
  { variant_id: "F16-html-q4-d", selected_option_id: "F16-html-q4-d-opt4" },
  { variant_id: "F16-html-q5-e", selected_option_id: "F16-html-q5-e-opt1" },
];
// Fixture token: base64url of the public schema label {"schema":"luban_practice_projection_receipt.v1"} — not a credential.
var PROJECTION_RECEIPT = "eyJzY2hlbWEiOiJsdWJhbl9wcmFjdGljZV9wcm9qZWN0aW9uX3JlY2VpcHQudjEifQ"; // pragma: allowlist secret
var PLAIN_ANSWERS = JSON.stringify(CANONICAL_ANSWERS);
var ENCODED_ANSWERS = encodeURIComponent(PLAIN_ANSWERS);       // DevTools death shape: %5B%7B%22...
var DOUBLE_ENCODED_ANSWERS = encodeURIComponent(ENCODED_ANSWERS); // %255B%257B%2522...

function bridgeQuery(answers, receipt) {
  return { presentation: "receipt", projection_receipt: receipt, answers: answers };
}

// parseBridgeReceipt runs inside a vm sandbox realm, so JSON.parse there yields objects
// whose prototype belongs to that realm; deepStrictEqual checks prototypes and would reject
// otherwise-identical objects. Round-trip through this realm's JSON to compare by value.
function normalize(value) {
  return JSON.parse(JSON.stringify(value));
}

// Guard: the fixture reproduces the exact QA death shape.
assert.ok(ENCODED_ANSWERS.indexOf("%5B%7B%22") === 0, "encoded fixture must start with the QA death prefix %5B%7B%22");
assert.ok(ENCODED_ANSWERS.length > 400, "encoded fixture must reproduce the multi-hundred-char percent-encoded death shape (QA measured ~790)");
assert.ok(DOUBLE_ENCODED_ANSWERS.indexOf("%25") === 0, "double-encoded fixture must carry %25");

// 1) Percent-encoded answers (the failing DevTools path) must parse to the canonical object.
var fromEncoded = parseBridgeReceipt(bridgeQuery(ENCODED_ANSWERS, PROJECTION_RECEIPT), "forward");
assert.ok(fromEncoded && fromEncoded.requested === true, "percent-encoded answers must not fall through to content_updated_retake");
assert.deepStrictEqual(normalize(fromEncoded.answers), CANONICAL_ANSWERS, "decoded answers must equal the canonical five-answer payload");
assert.strictEqual(fromEncoded.projectionReceipt, PROJECTION_RECEIPT, "projection receipt must survive the bridge unchanged");

// 2) Already-decoded answers (real-device web-view JSSDK auto-decode path) must also parse — same object.
var fromPlain = parseBridgeReceipt(bridgeQuery(PLAIN_ANSWERS, PROJECTION_RECEIPT), "forward");
assert.ok(fromPlain && fromPlain.requested === true, "already-decoded answers must still parse (idempotent decode)");
assert.deepStrictEqual(normalize(fromPlain.answers), CANONICAL_ANSWERS, "plain-input answers must equal the canonical payload");
assert.deepStrictEqual(normalize(fromPlain.answers), normalize(fromEncoded.answers), "encoded and plain inputs must yield the same object");

// 3) Double-encoded answers (%25...) must also decode cleanly (defensive against a second encode hop).
var fromDouble = parseBridgeReceipt(bridgeQuery(DOUBLE_ENCODED_ANSWERS, PROJECTION_RECEIPT), "forward");
assert.ok(fromDouble && fromDouble.requested === true, "double-encoded answers must decode through both layers");
assert.deepStrictEqual(normalize(fromDouble.answers), CANONICAL_ANSWERS, "double-decoded answers must equal the canonical payload");

// 4) A percent-encoded projection receipt (defensive) must be decoded back to its token form.
var encodedReceiptQuery = bridgeQuery(ENCODED_ANSWERS, encodeURIComponent("tok en+with/space")); // forces '%' in receipt
var fromEncodedReceipt = parseBridgeReceipt(encodedReceiptQuery, "forward");
assert.ok(fromEncodedReceipt && fromEncodedReceipt.requested === true, "percent-encoded receipt must still yield a usable bridge");
assert.strictEqual(fromEncodedReceipt.projectionReceipt, "tok en+with/space", "percent-encoded receipt must be decoded to its raw token");

// 5) Genuinely malformed answers (not JSON, even after decode) must still fall back to content_updated_retake (null).
var fromGarbage = parseBridgeReceipt(bridgeQuery("not-json-at-all", PROJECTION_RECEIPT), "forward");
assert.strictEqual(fromGarbage, null, "unrecoverable answers must still return null so the retake fallback fires");

// 6) Non-bridge modes are untouched.
var notForward = parseBridgeReceipt(bridgeQuery(ENCODED_ANSWERS, PROJECTION_RECEIPT), "review");
assert.deepStrictEqual(normalize(notForward), { requested: false, projectionReceipt: "", answers: [] }, "review mode must not consume the bridge");

console.log("PASS test_retest_bridge_decode.js");
