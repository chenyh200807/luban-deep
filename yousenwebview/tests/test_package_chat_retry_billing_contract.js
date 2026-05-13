// test_package_chat_retry_billing_contract.js — package retry should create a billable turn without duplicating the visible user bubble
// Run: node yousenwebview/tests/test_package_chat_retry_billing_contract.js

var fs = require("fs");
var path = require("path");

var chatSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);
var wsStreamSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/utils/ws-stream.js"),
  "utf8",
);

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

assert(
  chatSource.indexOf("var reuseUserMessage = !!sendOptions.reuseUserMessage;") >= 0,
  "package chat send pipeline should have an explicit retry presentation mode",
);
assert(
  chatSource.indexOf(
    "var msgs = reuseUserMessage ? existing.concat([aiMsg]) : existing.concat([userMsg, aiMsg]);",
  ) >= 0,
  "package retry should reuse the existing user message and only append a new assistant placeholder",
);
assert(
  chatSource.indexOf("reuseUserMessage: true") >= 0 &&
    chatSource.indexOf("persistUserMessage: false") >= 0,
  "package retry action should request no duplicate persisted user message",
);
assert(
  wsStreamSource.indexOf("startTurnPayload.persist_user_message = false") >= 0,
  "package retry should still go through start-turn while marking the user message as already persisted",
);

console.log("PASS test_package_chat_retry_billing_contract.js");
