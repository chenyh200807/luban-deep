// utils/chat-turn-recovery.js — chat turn recovery helpers

function normalizeMessageText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim();
}

function findRecoveredAssistant(messages, baselineCount, query) {
  if (!Array.isArray(messages) || !messages.length) return null;
  var normalizedQuery = normalizeMessageText(query);
  if (!normalizedQuery) return null;

  var startIndex = Math.max(0, Number(baselineCount) || 0);
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
        return {
          userIndex: i,
          assistantIndex: j,
          userMessage: current,
          assistantMessage: candidate,
        };
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
