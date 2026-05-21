// test_answer_leak_attack.js — 答案/采分点泄露 negative-case 契约
// Run: node wx_miniprogram/tests/test_answer_leak_attack.js
//
// 用途：暴露当前 sanitizer 的覆盖边界，不修改业务代码。
//   * 已拦的路径（progressive_disclosure.sections × 4 关键词）：
//     marker 必须不出现在最终渲染状态里
//   * 已知泄露的路径（fallback_text / mcq.option.text / followup_context /
//     callout block）：marker 当前会出现在最终渲染状态里——本测试将这一事实
//     固定下来，作为"已知 known gap"的活清单。
//
// 任何一天这些"已知泄露"被 sanitizer 收紧，本测试会变红，提示作者：
//   - 把 fixture 的 must_be_blocked 从 false 改成 true
//   - 在 PR 描述里说明 sanitizer 路径扩展的具体范围

var path = require("path");
var fs = require("fs");
var aiMessageState = require("../utils/ai-message-state");

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
  // 把整个 state 序列化（含 renderableContent / blocks / mcqCards / progressiveDisclosure），
  // 然后 grep marker。这是 wxml 上能看到的所有 surface 的超集。
  var serialized = "";
  try {
    serialized = JSON.stringify(state);
  } catch (_) {
    serialized = "";
  }
  return serialized.indexOf(marker) >= 0;
}

var blockedCount = 0;
var knownLeakCount = 0;
var unexpectedLeakCount = 0;
var unexpectedFixCount = 0;

for (var i = 0; i < fixtures.length; i += 1) {
  var fixture = fixtures[i];
  var state = renderAttackPayload(fixture.payload);
  var leaked = markerAppearsInState(state, fixture.marker);

  if (fixture.must_be_blocked) {
    // 必须拦截：marker 不应出现在 state
    assert(
      !leaked,
      "[BLOCKED contract] " +
        fixture.name +
        " (" +
        fixture.attack_vector +
        "): marker " +
        fixture.marker +
        " MUST NOT appear in render state — sanitizer regression!",
    );
    if (!leaked) blockedCount += 1;
  } else {
    // 已知泄露：marker 当前会出现。如果哪天突然不出现了，说明有人收紧了
    // sanitizer——这是好事，但需要把 fixture 升级成 must_be_blocked=true，
    // 并把 minimum_fix_suggestion 删掉/挪到 CHANGELOG。
    assert(
      leaked,
      "[KNOWN-GAP contract] " +
        fixture.name +
        " (" +
        fixture.attack_vector +
        "): marker " +
        fixture.marker +
        " was previously leaking but is now blocked. " +
        "Good — please flip must_be_blocked to true and update CHANGELOG.",
    );
    if (leaked) {
      knownLeakCount += 1;
    } else {
      unexpectedFixCount += 1;
    }
  }
}

console.log("");
console.log("─── Attack surface coverage summary ───");
console.log("  ✓ blocked vectors:    " + blockedCount + " / " + fixtures.length);
console.log("  ⚠ known leak vectors: " + knownLeakCount + " / " + fixtures.length);
if (unexpectedFixCount > 0) {
  console.log("  🎉 newly fixed:       " + unexpectedFixCount + " (please flip fixture must_be_blocked=true)");
}
console.log("");
console.log("Known-gap vectors (current scope of leak) — each needs explicit ack before next release:");
for (var k = 0; k < fixtures.length; k += 1) {
  if (!fixtures[k].must_be_blocked) {
    console.log("  - " + fixtures[k].attack_vector + " → " + fixtures[k].name);
  }
}
console.log("");

if (fail) {
  console.error(errors.join("\n"));
  console.error("\nFAIL: " + fail + " assertions failed (" + pass + " passed)");
  process.exit(1);
}
console.log("PASS test_answer_leak_attack.js (" + pass + " assertions across " + fixtures.length + " attack vectors)");
process.exit(0);
