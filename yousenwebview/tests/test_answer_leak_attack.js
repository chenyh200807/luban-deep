// test_answer_leak_attack.js — yousenwebview 答案/采分点泄露 negative-case 契约
// Run: node yousenwebview/tests/test_answer_leak_attack.js
//
// yousenwebview 是真实微信小程序前端。这个测试直接固定 packageDeeptutor
// render state，避免只靠 wx_miniprogram 影子测试间接覆盖。

var path = require("path");
var fs = require("fs");
var aiMessageState = require("../packageDeeptutor/utils/ai-message-state");

var FIXTURE_PATH = path.join(
  __dirname,
  "..",
  "..",
  "tests",
  "fixtures",
  "wechat_answer_leak_attack_cases.json",
);
var fixtures = JSON.parse(fs.readFileSync(FIXTURE_PATH, "utf8"));

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass += 1;
    return;
  }
  fail += 1;
  errors.push("FAIL: " + message);
}

function renderAttackPayload(payload) {
  return aiMessageState.deriveAiMessageRenderState({
    content: payload.content || "",
    presentation: payload.presentation || null,
    progressiveDisclosure: payload.progressiveDisclosure || null,
    parseBlocks: true,
  });
}

function markerAppearsInState(state, marker) {
  var serialized = "";
  try {
    serialized = JSON.stringify(state);
  } catch (_) {
    serialized = "";
  }
  return serialized.indexOf(marker) >= 0;
}

var blockedCount = 0;

for (var i = 0; i < fixtures.length; i += 1) {
  var fixture = fixtures[i];
  var state = renderAttackPayload(fixture.payload);
  var leaked = markerAppearsInState(state, fixture.marker);

  assert(
    !leaked,
    "[yousenwebview BLOCKED contract] " +
      fixture.name +
      " (" +
      fixture.attack_vector +
      "): marker " +
      fixture.marker +
      " MUST NOT appear in packageDeeptutor render state",
  );
  if (!leaked) blockedCount += 1;
}

console.log("");
console.log("─── yousenwebview attack surface coverage summary ───");
console.log("  ✓ blocked vectors: " + blockedCount + " / " + fixtures.length);
console.log("");

if (fail) {
  console.error(errors.join("\n"));
  console.error("\nFAIL: " + fail + " assertions failed (" + pass + " passed)");
  process.exit(1);
}
console.log(
  "PASS test_answer_leak_attack.js (" +
    pass +
    " assertions across " +
    fixtures.length +
    " attack vectors)",
);
process.exit(0);
