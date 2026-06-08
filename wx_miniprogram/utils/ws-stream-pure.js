// utils/ws-stream-pure.js — wx.* 无关的 ws-stream 纯函数集合
// 抽离自 ws-stream.js，零行为变化。
// 目的：让 normalizeErrorMessage / resolveEventVisibility / buildStatusEvent /
// buildTurnSocketPayload / computeReconnectDelayMs 等纯函数可以在 Node /
// web harness 环境直接 require，做契约测试，无需 mock wx.*。

var RECONNECT_BASE_DELAY_MS = 400;
var RECONNECT_MAX_DELAY_MS = 4000;
var RECONNECT_MAX_ATTEMPTS = 5;

function inferConversationTitle(query) {
  var text = String(query || "").trim();
  if (!text) return "";
  return text.length > 50 ? text.slice(0, 50) + "..." : text;
}

function buildPresentationEvent(resultMetadata) {
  var presentation = resultMetadata && resultMetadata.presentation;
  if (!presentation || typeof presentation !== "object") return null;
  return presentation;
}

function extractResultCitations(resultMetadata) {
  if (!resultMetadata || typeof resultMetadata !== "object") return [];
  var bundle = resultMetadata.citation_bundle;
  if (!bundle && resultMetadata.metadata && typeof resultMetadata.metadata === "object") {
    bundle = resultMetadata.metadata.citation_bundle;
  }
  if (bundle && Array.isArray(bundle.refs)) return bundle.refs.map(toDisplayCitation);
  return [];
}

function toDisplayCitation(ref) {
  var raw = ref && typeof ref === "object" ? ref : {};
  return {
    key: String(raw.key || "").trim(),
    marker: String(raw.marker || "").trim(),
    sourceType: String(raw.source_type || raw.sourceType || "").trim(),
    title: String(raw.title || "").trim(),
    locator: String(raw.locator || "").trim(),
    quote: String(raw.public_quote || raw.quote || "").trim(),
  };
}

function copyRuntimeDiagnosticFields(finalEvent, resultMetadata) {
  var nested =
    resultMetadata && resultMetadata.metadata && typeof resultMetadata.metadata === "object"
      ? resultMetadata.metadata
      : {};
  var keys = [
    "api_base",
    "release_id",
    "grading_engine_version",
    "v1_case_graded",
    "score_authority",
    "grading_rubric_provenance",
  ];
  for (var i = 0; i < keys.length; i++) {
    var key = keys[i];
    if (Object.prototype.hasOwnProperty.call(resultMetadata, key)) {
      finalEvent[key] = resultMetadata[key];
    } else if (Object.prototype.hasOwnProperty.call(nested, key)) {
      finalEvent[key] = nested[key];
    }
  }
}

function buildFinalResponseEvent(resultMetadata) {
  if (!resultMetadata || typeof resultMetadata !== "object") return null;
  var response = resultMetadata.response;
  if (typeof response !== "string" && resultMetadata.metadata && typeof resultMetadata.metadata === "object") {
    response = resultMetadata.metadata.response;
  }
  if (typeof response !== "string" || !response.trim()) return null;
  var finalEvent = {
    type: "final",
    engine: "tutorbot",
    response: response,
  };
  copyRuntimeDiagnosticFields(finalEvent, resultMetadata);
  var citations = extractResultCitations(resultMetadata);
  if (citations.length) finalEvent.citations = citations;
  return finalEvent;
}

function normalizeErrorMessage(err) {
  var raw = "";
  if (typeof err === "string") {
    raw = err;
  } else if (err) {
    raw = err.errMsg || err.message || err.reason || "";
  }
  raw = String(raw || "").trim();
  if (!raw) return "连接失败，请重试";
  if (raw === "AUTH_EXPIRED") return "登录已失效，请重新登录";
  if (raw === "REQUEST_ABORTED") return "本轮已取消";
  if (/timeout|timed out|超时/i.test(raw)) return "请求超时，请稍后重试";
  if (/^NETWORK_ERROR:/i.test(raw)) return "连接服务器失败，请检查网络后重试";
  var http = raw.match(/^HTTP_(\d+):/i);
  if (http) {
    var status = parseInt(http[1], 10) || 0;
    if (status === 401) return "登录已失效，请重新登录";
    if (status === 429) return "操作过于频繁，请稍后再试";
    if (status >= 500) return "服务暂时不可用，请稍后重试";
    return "请求失败，请稍后重试";
  }
  if (
    /Internal Server Error|provider error|raw provider|DataInspectionFailed|Authentication Fails|api key|read_file|write_file|list_dir|HEARTBEAT|traceback|stack trace|workspace/i.test(raw)
  ) {
    return "服务暂时不可用，请稍后重试";
  }
  return raw;
}

function resolveEventVisibility(event) {
  if (!event || typeof event !== "object") return "public";
  var direct = String(event.visibility || "").trim().toLowerCase();
  if (direct === "internal") return "internal";
  var metadata = event.metadata || {};
  var nested = String(metadata.visibility || "").trim().toLowerCase();
  return nested === "internal" ? "internal" : "public";
}

function computeReconnectDelayMs(attempt) {
  var safeAttempt = Math.max(1, Number(attempt) || 1);
  return Math.min(
    RECONNECT_MAX_DELAY_MS,
    RECONNECT_BASE_DELAY_MS * Math.pow(2, safeAttempt - 1),
  );
}

function buildTurnSocketPayload(turnId, lastSeq) {
  var resolvedTurnId = String(turnId || "").trim();
  if (!resolvedTurnId) return null;
  var resolvedSeq = Number(lastSeq) || 0;
  if (resolvedSeq > 0) {
    return {
      type: "resume_from",
      turn_id: resolvedTurnId,
      seq: resolvedSeq,
    };
  }
  return {
    type: "subscribe_turn",
    turn_id: resolvedTurnId,
    after_seq: 0,
  };
}

function buildStatusEvent(event) {
  if (!event || typeof event !== "object") return null;
  var eventType = String(event.type || "").trim();
  if (["thinking", "progress", "observation", "stage_start", "tool_call", "tool_result"].indexOf(eventType) === -1) {
    return null;
  }

  var eventMetadata = event.metadata || {};
  var visibility = resolveEventVisibility(event);
  var stage = String(event.stage || "").trim();
  var content = String(event.content || "");
  var toolName =
    String(event.tool_name || eventMetadata.tool_name || eventMetadata.tool || "").trim() ||
    (eventType === "tool_call" ? content : "");
  var metadata = Object.assign({}, eventMetadata, {
    visibility: visibility,
  });

  if (visibility === "internal" && eventType === "progress") {
    return null;
  }

  if (visibility === "internal" && (eventType === "thinking" || eventType === "observation")) {
    metadata.sanitized_internal = true;
    content = "";
  }

  return {
    type: "status",
    data: content || stage || eventType,
    content: content,
    source: event.source || "",
    stage: stage,
    eventType: eventType,
    toolName: toolName,
    metadata: metadata,
    seq: typeof event.seq === "number" ? event.seq : 0,
  };
}

module.exports = {
  RECONNECT_BASE_DELAY_MS: RECONNECT_BASE_DELAY_MS,
  RECONNECT_MAX_DELAY_MS: RECONNECT_MAX_DELAY_MS,
  RECONNECT_MAX_ATTEMPTS: RECONNECT_MAX_ATTEMPTS,
  inferConversationTitle: inferConversationTitle,
  buildPresentationEvent: buildPresentationEvent,
  buildFinalResponseEvent: buildFinalResponseEvent,
  normalizeErrorMessage: normalizeErrorMessage,
  resolveEventVisibility: resolveEventVisibility,
  computeReconnectDelayMs: computeReconnectDelayMs,
  buildTurnSocketPayload: buildTurnSocketPayload,
  buildStatusEvent: buildStatusEvent,
};
