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

run("can recover by client turn id when server turn id is not projected after resume", function () {
  var messages = [
    { role: "user", content: "案例题批改", metadata: { client_turn_id: "client_resume_1" } },
    { role: "assistant", content: "当前批改结果" },
  ];

  var found = recovery.findRecoveredAssistant(messages, {
    baselineCount: 100,
    query: "案例题批改",
    turnId: "turn_resume_1",
    clientTurnId: "client_resume_1",
  });

  assert(
    !!found,
    "client turn id should recover the pending answer when server turn id is temporarily absent",
  );
  assertEqual(found.assistantIndex, 1, "client turn id fallback should bind to the same user turn");
});

run("does not recover assistant answer from metadata response without canonical content", function () {
  var messages = [
    { role: "user", content: "案例题批改", client_turn_id: "client_meta_1" },
    {
      role: "assistant",
      content: "",
      metadata: { response: "当前批改结果已经写入终态 metadata" },
      engine_turn_id: "turn_meta_1",
    },
  ];

  var found = recovery.findRecoveredAssistant(messages, {
    baselineCount: 100,
    query: "案例题批改",
    turnId: "turn_meta_1",
    clientTurnId: "client_meta_1",
  });

  assert(!found, "metadata.response must not clear pending turn recovery without content");
  assertEqual(
    recovery.getAssistantDisplayText(messages[1]),
    "",
    "display text should come from canonical assistant content only",
  );
});

run("does not recover assistant answer from metadata content", function () {
  var messages = [
    { role: "user", content: "案例题批改", client_turn_id: "client_content_1" },
    {
      role: "assistant",
      content: "",
      metadata: {
        content: "不应恢复的内部 content",
        metadata: { content: "不应恢复的嵌套内部 content" },
      },
      engine_turn_id: "turn_content_1",
    },
  ];

  var found = recovery.findRecoveredAssistant(messages, {
    baselineCount: 100,
    query: "案例题批改",
    turnId: "turn_content_1",
    clientTurnId: "client_content_1",
  });

  assert(!found, "metadata.content must not count as recovered assistant content");
  assertEqual(
    recovery.getAssistantDisplayText(messages[1]),
    "",
    "metadata.content must not be displayed as assistant answer",
  );
});

run("does not recover assistant answer from metadata content", function () {
  var messages = [
    { role: "user", content: "案例题批改", client_turn_id: "client_content_1" },
    {
      role: "assistant",
      content: "",
      metadata: {
        content: "不应恢复的内部 content",
        metadata: { content: "不应恢复的嵌套内部 content" },
      },
      engine_turn_id: "turn_content_1",
    },
  ];

  var found = recovery.findRecoveredAssistant(messages, {
    baselineCount: 100,
    query: "案例题批改",
    turnId: "turn_content_1",
    clientTurnId: "client_content_1",
  });

  assert(!found, "metadata.content must not count as recovered assistant content");
  assertEqual(
    recovery.getAssistantDisplayText(messages[1]),
    "",
    "metadata.content must not be displayed as assistant answer",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_chat_turn_recovery.js (" + pass + " assertions)");
