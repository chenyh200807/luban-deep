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
  "PENDING_TURN_FOREGROUND_MAX_ATTEMPTS",
  "foreground recovery should use a short bounded window instead of treating empty done as terminal success",
);
assertContains(
  "_finishPendingTurnRecovery: function (serverMessages, options)",
  "pending turn recovery should have an explicit terminal path for unrecovered cold starts",
);
assert(
  /self\._finishPendingTurnRecovery\(\s*opts\.longPoll \|\| opts\.unlockOnExhausted\s*\?\s*serverMessages\s*:\s*null,\s*\{\s*keepPending:\s*!!opts\.keepPendingOnExhausted,\s*hydrate:\s*opts\.hydrateOnExhausted !== false/.test(source),
  "unrecovered empty-done responses should unlock without erasing pending identity or hydrating incomplete history",
);
assertContains(
  "keepPendingOnExhausted: true",
  "empty done and foreground recovery should preserve pending identity while canonical history catches up",
);
assertContains(
  "hydrateOnExhausted: false",
  "empty done recovery exhaustion must not replace the local turn with incomplete server history",
);
assert(
  /_startPendingTurnBackgroundRecovery:\s*function[\s\S]*?keepPendingOnExhausted:\s*true,\s*hydrateOnExhausted:\s*false,/.test(source),
  "foreground/background pending recovery must not hydrate incomplete server history over local pending UI",
);
assertContains(
  "self._finishPendingTurnRecovery();",
  "recovery fetch exhaustion should unlock the chat even when no messages can be loaded",
);
assertContains(
  "err && err.statusCode === 404",
  "missing conversations should terminate recovery immediately instead of polling or switching base",
);
assertContains(
  'wx.getStorageSync("current_session_id") === pending.conversationId',
  "missing pending conversations should clear the stale current session pointer",
);
assertContains(
  'wx.getStorageSync("current_session_id") === convId',
  "missing restored conversations should clear the stale current session pointer",
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
  /_onDone:\s*function\s*\(options\)[\s\S]*?var wasRecoveringTurn = !!this\._recoveringTurn;[\s\S]*?var renderedAnswer = false;[\s\S]*?!skipHistoryRecovery && !renderedAnswer[\s\S]*?_recoverTurnFromHistory\(/.test(source),
  "terminal done without a visible answer should preserve pending identity and recover from canonical history",
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
