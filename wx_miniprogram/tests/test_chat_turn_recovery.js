// test_chat_turn_recovery.js — regression tests for wx_miniprogram/utils/chat-turn-recovery.js
// Run: node wx_miniprogram/tests/test_chat_turn_recovery.js

var recovery = require("../utils/chat-turn-recovery");

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

run("finds recovered assistant after pending user turn", function () {
  var messages = [
    { role: "user", content: "旧问题" },
    { role: "assistant", content: "旧回答" },
    { role: "user", content: "模板起拱高度是多少？" },
    { role: "assistant", content: "跨度大于4m时，按跨度的1/1000~3/1000起拱。" },
  ];

  var found = recovery.findRecoveredAssistant(messages, 2, "模板起拱高度是多少？");
  assert(!!found, "should recover the assistant reply");
  assertEqual(found.assistantIndex, 3, "assistant index should match recovered reply");
});

run("ignores suffix that only persisted the user message", function () {
  var messages = [
    { role: "user", content: "旧问题" },
    { role: "assistant", content: "旧回答" },
    { role: "user", content: "模板起拱高度是多少？" },
  ];

  assert(
    !recovery.hasRecoveredAssistant(messages, 2, "模板起拱高度是多少？"),
    "user-only suffix should not be treated as recovered",
  );
});

run("stops at the next user turn when no assistant answer exists", function () {
  var messages = [
    { role: "user", content: "旧问题" },
    { role: "assistant", content: "旧回答" },
    { role: "user", content: "模板起拱高度是多少？" },
    { role: "user", content: "另一个问题" },
    { role: "assistant", content: "另一个回答" },
  ];

  assert(
    !recovery.hasRecoveredAssistant(messages, 2, "模板起拱高度是多少？"),
    "next user turn should terminate recovery scan for the pending query",
  );
});

run("normalizes whitespace before matching query", function () {
  var messages = [
    { role: "user", content: "旧问题" },
    { role: "assistant", content: "旧回答" },
    { role: "user", content: "模板起拱高度是多少？" },
    { role: "assistant", content: "  跨度大于4m时应起拱。  " },
  ];

  assert(
    recovery.hasRecoveredAssistant(messages, 2, " 模板起拱高度是多少？ "),
    "query whitespace differences should still match the recovered turn",
  );
});

run("ignores identical historical query before the current baseline", function () {
  var messages = [
    { role: "user", content: "模板起拱高度是多少？" },
    { role: "assistant", content: "历史回答" },
    { role: "user", content: "模板起拱高度是多少？" },
  ];

  assert(
    !recovery.hasRecoveredAssistant(messages, 2, "模板起拱高度是多少？"),
    "baseline should prevent matching an older identical query",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_chat_turn_recovery.js (" + pass + " assertions)");
