// test_package_chat_turn_recovery.js — package regression tests for chat-turn-recovery.js
// Run: node yousenwebview/tests/test_package_chat_turn_recovery.js

var recovery = require("../packageDeeptutor/utils/chat-turn-recovery");

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

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
    pass++;
    return;
  }
  fail++;
  errors.push(
    "FAIL: " +
      message +
      "\n  expected: " +
      JSON.stringify(expected) +
      "\n  actual:   " +
      JSON.stringify(actual),
  );
}

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

run("prefers server turn identity over query and local baseline", function () {
  var messages = [
    { role: "user", content: "模板起拱高度是多少？" },
    { role: "assistant", content: "历史回答", engine_turn_id: "turn_old" },
    { role: "user", content: "模板起拱高度是多少？" },
    { role: "assistant", content: "当前回答", engine_turn_id: "turn_current" },
  ];

  var found = recovery.findRecoveredAssistant(messages, {
    baselineCount: 100,
    query: "模板起拱高度是多少？",
    turnId: "turn_current",
  });

  assert(!!found, "turn id should recover even when local baseline was truncated");
  assertEqual(found.assistantMessage.content, "当前回答", "turn id should select the current answer");
});

run("does not fall back to an older identical query when turn id is known", function () {
  var messages = [
    { role: "user", content: "模板起拱高度是多少？" },
    { role: "assistant", content: "历史回答", engine_turn_id: "turn_old" },
  ];

  assert(
    !recovery.hasRecoveredAssistant(messages, {
      baselineCount: 0,
      query: "模板起拱高度是多少？",
      turnId: "turn_current",
    }),
    "known turn id should prevent query fallback from recovering an older repeated answer",
  );
});

run("can recover by client turn id before server turn id is known", function () {
  var messages = [
    { role: "user", content: "模板起拱高度是多少？", client_turn_id: "client_1" },
    { role: "assistant", content: "当前回答" },
  ];

  var found = recovery.findRecoveredAssistant(messages, {
    baselineCount: 100,
    query: "模板起拱高度是多少？",
    clientTurnId: "client_1",
  });

  assert(!!found, "client turn id should recover even before engine turn id is available");
  assertEqual(found.assistantIndex, 1, "client turn id should bind to the assistant after that user turn");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_chat_turn_recovery.js (" + pass + " assertions)");
