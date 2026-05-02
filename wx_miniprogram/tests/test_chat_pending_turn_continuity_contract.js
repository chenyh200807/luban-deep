// Ensures sent chat turns survive page/background navigation unless the user stops them.
// Run: node wx_miniprogram/tests/test_chat_pending_turn_continuity_contract.js

var fs = require("fs");
var path = require("path");

var source = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.js"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

function assertContains(fragment, message) {
  assert(source.indexOf(fragment) >= 0, message);
}

assertContains(
  "CHAT_PENDING_TURN_KEY",
  "chat page should define a durable pending-turn storage key",
);
assertContains(
  "wx.setStorageSync(CHAT_PENDING_TURN_KEY",
  "pending turns should be written to local storage after a question is sent",
);
assertContains(
  "self._persistPendingTurn({",
  "sending a question should persist the pending turn immediately, not wait for page teardown",
);
assertContains(
  "clientTurnId: _turnId",
  "pending turn storage should keep the client turn id for stable recovery identity",
);
assertContains(
  "wx.getStorageSync(CHAT_PENDING_TURN_KEY",
  "chat page should reload pending turns after page recreation",
);
assertContains(
  "wx.removeStorageSync(CHAT_PENDING_TURN_KEY",
  "pending turns should be cleared only after terminal recovery or user cancellation",
);
assertContains(
  "PENDING_TURN_POLL_MAX_ATTEMPTS",
  "recovery should poll long enough for slow answers instead of only checking a few times",
);
assertContains(
  "_finishPendingTurnRecovery: function (serverMessages)",
  "pending turn recovery should have an explicit terminal path for unrecovered cold starts",
);
assertContains(
  "self._finishPendingTurnRecovery(opts.longPoll ? serverMessages : null);",
  "unrecovered server responses should hydrate or unlock the chat instead of leaving streaming stuck",
);
assertContains(
  "self._finishPendingTurnRecovery();",
  "recovery fetch exhaustion should unlock the chat even when no messages can be loaded",
);
assertContains(
  "isStreaming: false,",
  "pending turn terminal recovery should return the chat surface to a sendable state",
);
assertContains(
  "[\"messages[\" + failedIdx + \"].streaming\"]: false",
  "failed local AI message should stop streaming when short recovery is exhausted",
);
assert(
  source.indexOf("this._clearPendingTurn();\n    this._recoveringTurn = false;") < 0,
  "non-cancelling local stream aborts must not erase the durable pending turn",
);
assert(
  /stopStream:\s*function[\s\S]*?_stop\(\{\s*cancelTurn:\s*true\s*\}\)/.test(source),
  "only the explicit stop button should request server-side turn cancellation",
);
assert(
  !/clearMessages:\s*function[\s\S]{0,120}?_stop\(\{\s*cancelTurn:\s*true\s*\}\)/.test(source),
  "clearing, switching, or leaving the page must not cancel an already-sent turn",
);

console.log("PASS test_chat_pending_turn_continuity_contract.js");
