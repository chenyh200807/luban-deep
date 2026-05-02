// utils/chat-turn-recovery.js — chat turn recovery helpers

function normalizeMessageText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim();
}

function _pendingFromArgs(baselineOrPending, query) {
  if (baselineOrPending && typeof baselineOrPending === "object") {
    return {
      baselineCount: Math.max(0, Number(baselineOrPending.baselineCount) || 0),
      query: String(baselineOrPending.query || ""),
      turnId: String(baselineOrPending.turnId || baselineOrPending.turn_id || "").trim(),
      clientTurnId: String(
        baselineOrPending.clientTurnId || baselineOrPending.client_turn_id || "",
      ).trim(),
    };
  }
  return {
    baselineCount: Math.max(0, Number(baselineOrPending) || 0),
    query: String(query || ""),
    turnId: "",
    clientTurnId: "",
  };
}

function _messageMetadata(message) {
  return message && message.metadata && typeof message.metadata === "object"
    ? message.metadata
    : {};
}

function _messageTurnId(message) {
  var metadata = _messageMetadata(message);
  return String(
    (message && (message.engine_turn_id || message.turn_id || message.engineTurnId)) ||
      metadata.engine_turn_id ||
      metadata.turn_id ||
      "",
  ).trim();
}

function _messageClientTurnId(message) {
  var metadata = _messageMetadata(message);
  return String(
    (message && (message.client_turn_id || message.clientTurnId)) ||
      metadata.client_turn_id ||
      metadata.clientTurnId ||
      "",
  ).trim();
}

function _result(userIndex, assistantIndex, messages) {
  return {
    userIndex: userIndex,
    assistantIndex: assistantIndex,
    userMessage: userIndex >= 0 ? messages[userIndex] : null,
    assistantMessage: messages[assistantIndex],
  };
}

function _findByTurnIdentity(messages, pending) {
  if (pending.turnId) {
    for (var i = 0; i < messages.length; i++) {
      var candidate = messages[i];
      if (
        candidate &&
        String(candidate.role || "") === "assistant" &&
        normalizeMessageText(candidate.content) &&
        _messageTurnId(candidate) === pending.turnId
      ) {
        var userIndex = -1;
        for (var back = i - 1; back >= 0; back--) {
          if (String((messages[back] && messages[back].role) || "") === "user") {
            userIndex = back;
            break;
          }
        }
        return _result(userIndex, i, messages);
      }
    }
    return null;
  }

  if (!pending.clientTurnId) return null;
  for (var j = 0; j < messages.length; j++) {
    var current = messages[j];
    if (!current || String(current.role || "") !== "user") continue;
    if (_messageClientTurnId(current) !== pending.clientTurnId) continue;
    for (var k = j + 1; k < messages.length; k++) {
      var next = messages[k];
      if (!next) continue;
      var role = String(next.role || "");
      if (role === "assistant" && normalizeMessageText(next.content)) {
        return _result(j, k, messages);
      }
      if (role === "user") break;
    }
  }
  return null;
}

function findRecoveredAssistant(messages, baselineCount, query) {
  if (!Array.isArray(messages) || !messages.length) return null;
  var pending = _pendingFromArgs(baselineCount, query);
  var identityMatch = _findByTurnIdentity(messages, pending);
  if (identityMatch || pending.turnId) return identityMatch;

  var normalizedQuery = normalizeMessageText(pending.query);
  if (!normalizedQuery) return null;

  var startIndex = pending.baselineCount;
  if (messages.length < startIndex + 2) return null;

  for (var i = startIndex; i < messages.length; i++) {
    var current = messages[i];
    if (!current || String(current.role || "") !== "user") continue;
    if (normalizeMessageText(current.content) !== normalizedQuery) continue;

    for (var j = i + 1; j < messages.length; j++) {
      var candidate = messages[j];
      if (!candidate) continue;
      var role = String(candidate.role || "");
      if (role === "assistant" && normalizeMessageText(candidate.content)) {
        return _result(i, j, messages);
      }
      if (role === "user") {
        break;
      }
    }
  }

  return null;
}

function hasRecoveredAssistant(messages, baselineCount, query) {
  return !!findRecoveredAssistant(messages, baselineCount, query);
}

module.exports = {
  normalizeMessageText: normalizeMessageText,
  findRecoveredAssistant: findRecoveredAssistant,
  hasRecoveredAssistant: hasRecoveredAssistant,
};
