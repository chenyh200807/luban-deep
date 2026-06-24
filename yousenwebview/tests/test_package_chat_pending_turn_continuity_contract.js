// Ensures sent chat turns survive package page/background navigation unless the user stops them.
// Run: node yousenwebview/tests/test_package_chat_pending_turn_continuity_contract.js

var fs = require("fs");
var path = require("path");

var source = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);

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
  "package chat page should define a durable pending-turn storage key",
);
assertContains(
  "wx.setStorageSync(CHAT_PENDING_TURN_KEY",
  "pending turns should be written to local storage after a question is sent",
);
assertContains(
  "self._persistPendingTurn({",
  "existing package conversations should persist the pending turn immediately, not wait for page teardown",
);
assert(
  /onStarted:\s*function\s*\(payload\)[\s\S]*?self\._persistPendingTurn\(\s*Object\.assign\(\{\},\s*pendingDraft,\s*\{[\s\S]*?conversationId:\s*startedSessionId,[\s\S]*?turnId:\s*startedTurnId/.test(source),
  "new package conversations must persist pending identity as soon as start-turn returns canonical conversation and turn ids",
);
assertContains(
  "clientTurnId: _turnId",
  "pending turn storage should keep the client turn id for stable recovery identity",
);
assertContains(
  "wx.getStorageSync(CHAT_PENDING_TURN_KEY",
  "package chat page should reload pending turns after page recreation",
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
  "_finishPendingTurnRecovery: function (serverMessages, options)",
  "package pending turn recovery should have an explicit terminal path for unrecovered cold starts",
);
assertContains(
  "keepPendingOnExhausted",
  "package foreground recovery should unlock input without erasing a still-slow pending turn",
);
assertContains(
  "PENDING_TURN_FOREGROUND_MAX_ATTEMPTS",
  "package cold-start recovery should use a short foreground window instead of locking the chat for long polling",
);
assert(
  /_onDone:\s*function[\s\S]*?_recoverTurnFromHistory\(\{\s*maxAttempts:\s*PENDING_TURN_FOREGROUND_MAX_ATTEMPTS,/.test(source),
  "package done-event recovery should use the shared foreground attempt budget",
);
assertContains(
  "_continuePendingTurnRecoveryInBackground: function ()",
  "package short foreground recovery exhaustion should continue long canonical history recovery without blocking the UI",
);
assert(
  /_continuePendingTurnRecoveryInBackground:\s*function\s*\(\)[\s\S]*?longPoll:\s*true/.test(source),
  "package background continuation should reuse canonical history recovery with long polling",
);
assertContains(
  "opts.longPoll || opts.unlockOnExhausted ? serverMessages : null",
  "package unrecovered server responses should hydrate or unlock the chat instead of leaving streaming stuck",
);
assertContains(
  "hydrateOnExhausted: false",
  "package empty done recovery exhaustion must not replace the local turn with incomplete server history",
);
assert(
  /_startPendingTurnBackgroundRecovery:\s*function[\s\S]*?keepPendingOnExhausted:\s*true,\s*hydrateOnExhausted:\s*false,/.test(source),
  "package foreground/background recovery must not hydrate incomplete server history over local pending UI",
);
assertContains(
  "self._finishPendingTurnRecovery();",
  "package recovery fetch exhaustion should unlock the chat even when no messages can be loaded",
);
assertContains(
  "err && err.statusCode === 404",
  "package missing conversations should terminate recovery immediately instead of polling or switching base",
);
assertContains(
  'wx.getStorageSync("current_session_id") === pending.conversationId',
  "package missing pending conversations should clear the stale current session pointer",
);
assertContains(
  'wx.getStorageSync("current_session_id") === convId',
  "package missing restored conversations should clear the stale current session pointer",
);
assertContains(
  "isStreaming: false,",
  "package pending turn terminal recovery should return the chat surface to a sendable state",
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
  "clearing, switching, or leaving the package page must not cancel an already-sent turn",
);

console.log("PASS test_package_chat_pending_turn_continuity_contract.js");
