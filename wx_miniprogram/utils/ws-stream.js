// utils/ws-stream.js — start-turn + /api/v1/ws 流式引擎
const auth = require("./auth");
const api = require("./api");
const endpoints = require("./endpoints");
const wsPure = require("./ws-stream-pure");

var inferConversationTitle = wsPure.inferConversationTitle;
var buildPresentationEvent = wsPure.buildPresentationEvent;
var buildFinalResponseEvent = wsPure.buildFinalResponseEvent;
var normalizeErrorMessage = wsPure.normalizeErrorMessage;
var resolveEventVisibility = wsPure.resolveEventVisibility;
var computeReconnectDelayMs = wsPure.computeReconnectDelayMs;
var buildTurnSocketPayload = wsPure.buildTurnSocketPayload;
var buildStatusEvent = wsPure.buildStatusEvent;

var RECONNECT_BASE_DELAY_MS = wsPure.RECONNECT_BASE_DELAY_MS;
var RECONNECT_MAX_DELAY_MS = wsPure.RECONNECT_MAX_DELAY_MS;
var RECONNECT_MAX_ATTEMPTS = wsPure.RECONNECT_MAX_ATTEMPTS;

function socketUrlToApiBase(socketUrl) {
  var normalized = String(socketUrl || "").trim();
  if (normalized.indexOf("wss://") === 0)
    normalized = "https://" + normalized.slice(6);
  if (normalized.indexOf("ws://") === 0)
    normalized = "http://" + normalized.slice(5);
  return normalized.replace(/\/api\/v1\/ws(?:\?.*)?$/i, "");
}

function streamChat(opts, callbacks) {
  var cb = callbacks || {};
  var query = String((opts && opts.query) || "").trim();
  var sessionId = String((opts && opts.sessionId) || "").trim();
  var mode = String((opts && opts.mode) || "AUTO")
    .trim()
    .toUpperCase();
  var clientTurnId = String((opts && opts.clientTurnId) || "").trim();

  if (!query) {
    if (cb.onError) cb.onError("query is required");
    if (cb.onDone) cb.onDone();
    return function () {};
  }
  if (!sessionId) {
    if (cb.onError) cb.onError("会话初始化失败，请重试");
    if (cb.onDone) cb.onDone();
    return function () {};
  }

  var app = getApp();
  var aborted = false;
  var doneReceived = false;
  var firstTokenReceived = false;
  var finalFired = false;
  var idleTimer = null;
  var slowTimer = null;
  var reconnectTimer = null;
  var socketTask = null;
  var idleTimeoutMs = Number((opts && opts.idleTimeoutMs) || 60000) || 60000;
  var slowResponseMs = 15000;
  var botId = "";
  var chatId = sessionId;
  var turnId = "";
  var lastSeq = 0;
  var socketUrls = [];
  var connectedApiBase = "";
  var reconnectAttempts = 0;
  var socketOpen = false;
  var cancelRequested = false;
  var timeoutCancelRequested = false;
  var terminalWaitTicksAfterCancel = 0;
  var maxTerminalWaitTicksAfterCancel =
    Number((opts && opts.maxTerminalWaitTicksAfterCancel) || 3) || 3;
  var resumeAttempted = false;
  var resumeSucceeded = false;

  function emitTelemetry(eventName, metadata) {
    if (!cb.onTelemetryEvent) return;
    cb.onTelemetryEvent({
      eventName: eventName,
      sessionId: chatId || sessionId,
      turnId: turnId,
      metadata: metadata || {},
    });
  }

  function clearIdleTimer() {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
  }

  function sendCancelTurn(reason) {
    if (!socketOpen || !socketTask || !turnId) return false;
    try {
      socketTask.send({
        data: JSON.stringify({
          type: "cancel_turn",
          turn_id: turnId,
        }),
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  function resetIdleTimer() {
    clearIdleTimer();
    idleTimer = setTimeout(function () {
      if (!aborted && !doneReceived) {
        if (cancelRequested || timeoutCancelRequested) {
          terminalWaitTicksAfterCancel += 1;
          if (terminalWaitTicksAfterCancel <= maxTerminalWaitTicksAfterCancel) {
            if (cb.onStatus) {
              cb.onStatus({
                type: "status",
                data: "awaiting_terminal",
                content: "已发送停止请求，正在等待本轮结束…",
                eventType: "awaiting_terminal",
                metadata: {
                  visibility: "public",
                  reason: timeoutCancelRequested
                    ? "idle_timeout"
                    : "user_cancel",
                },
              });
            }
            resetIdleTimer();
            return;
          }
          failStream(
            "已发送停止请求，服务端暂未返回终态，请稍后在历史记录查看结果",
          );
          return;
        }
        if (!timeoutCancelRequested && sendCancelTurn("idle_timeout")) {
          timeoutCancelRequested = true;
          cancelRequested = true;
          terminalWaitTicksAfterCancel = 0;
          clearSlowTimer();
          if (cb.onStatus) {
            cb.onStatus({
              type: "status",
              data: "cancelling",
              content: "响应超时，正在停止本轮分析…",
              eventType: "cancelling",
              metadata: { visibility: "public", reason: "idle_timeout" },
            });
          }
          resetIdleTimer();
          return;
        }
        failStream("响应超时，请重试");
      }
    }, idleTimeoutMs);
  }

  function clearSlowTimer() {
    if (slowTimer) {
      clearTimeout(slowTimer);
      slowTimer = null;
    }
  }

  function clearReconnectTimer() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function startSlowTimer() {
    clearSlowTimer();
    slowTimer = setTimeout(function () {
      if (!aborted && !doneReceived && !firstTokenReceived) {
        if (cb.onStatus) cb.onStatus({ type: "status", data: "slow_response" });
      }
    }, slowResponseMs);
  }

  function failStream(err) {
    if (aborted || doneReceived) return;
    aborted = true;
    clearIdleTimer();
    clearSlowTimer();
    clearReconnectTimer();
    emitTelemetry("surface_render_failed", {
      message: normalizeErrorMessage(err),
    });
    if (cb.onError) cb.onError(normalizeErrorMessage(err));
    if (cb.onDone) cb.onDone();
    try {
      if (socketTask) socketTask.close({ code: 1000, reason: "abort" });
    } catch (_) {}
  }

  function scheduleReconnect(err) {
    if (aborted || doneReceived || reconnectTimer || !socketUrls.length)
      return false;
    if (reconnectAttempts >= RECONNECT_MAX_ATTEMPTS) return false;
    reconnectAttempts += 1;
    var delay = computeReconnectDelayMs(reconnectAttempts);
    var jitter = Math.floor(delay * 0.2 * Math.random());
    if (cb.onStatus) {
      cb.onStatus({
        type: "status",
        data: "reconnecting",
        content: "连接中断，正在恢复…",
        eventType: "reconnecting",
        metadata: {
          attempt: reconnectAttempts,
        },
      });
    }
    reconnectTimer = setTimeout(function () {
      reconnectTimer = null;
      if (aborted || doneReceived) return;
      connectTutorBotSocket();
    }, delay + jitter);
    return true;
  }

  function handleEvent(event) {
    if (!event || typeof event !== "object") return;
    var eventType = String(event.type || "").trim();
    var eventMetadata = event.metadata || {};
    var visibility = resolveEventVisibility(event);
    var eventSeq = typeof event.seq === "number" ? event.seq : null;
    if (event.turn_id) {
      turnId = String(event.turn_id || "").trim() || turnId;
    }
    if (event.session_id) {
      chatId = String(event.session_id || "").trim() || chatId;
    }

    if (eventType === "session") {
      if (eventMetadata.session_id) {
        chatId = String(eventMetadata.session_id || "").trim() || chatId;
      }
      if (eventMetadata.turn_id) {
        turnId = String(eventMetadata.turn_id || "").trim() || turnId;
      }
      emitTelemetry("session_event_received");
      return;
    }

    if (resumeAttempted && !resumeSucceeded && turnId) {
      resumeSucceeded = true;
      emitTelemetry("resume_succeeded", { event_type: eventType });
    }

    if (eventSeq !== null) {
      if (eventSeq <= lastSeq) {
        return;
      }
      lastSeq = eventSeq;
    }

    if (eventType === "content") {
      if (visibility !== "public") {
        return;
      }
      if (!firstTokenReceived) {
        firstTokenReceived = true;
        clearSlowTimer();
      }
      if (cb.onToken) cb.onToken(String(event.content || ""));
      return;
    }

    var statusEvent = buildStatusEvent(event);
    if (statusEvent) {
      if (cb.onStatus) {
        cb.onStatus(statusEvent);
      }
      return;
    }

    if (eventType === "result") {
      if (visibility !== "public") {
        return;
      }
      var presentationEvent = buildPresentationEvent(eventMetadata);
      if (presentationEvent && cb.onPresentation) {
        cb.onPresentation(presentationEvent);
      }
      var finalResponseEvent = buildFinalResponseEvent(eventMetadata);
      if (finalResponseEvent && cb.onFinal && !finalFired) {
        finalFired = true;
        if (!finalResponseEvent.api_base) {
          finalResponseEvent.api_base =
            connectedApiBase || endpoints.getPrimaryBaseUrl(false);
        }
        finalResponseEvent.engine_session_id = chatId || sessionId;
        finalResponseEvent.engine_turn_id = turnId;
        finalResponseEvent.bot_id = botId;
        cb.onFinal(finalResponseEvent);
      }
      return;
    }

    if (eventType === "error") {
      if (eventMetadata && eventMetadata.status === "cancelled") {
        doneReceived = true;
        clearIdleTimer();
        clearSlowTimer();
        clearReconnectTimer();
        if (cb.onStatusEnd) cb.onStatusEnd();
        if (cb.onDone) cb.onDone();
        try {
          if (socketTask) socketTask.close({ code: 1000, reason: "cancelled" });
        } catch (_) {}
        return;
      }
      if (eventMetadata && eventMetadata.turn_terminal) {
        failStream(String(event.content || "服务异常"));
        return;
      }
      // Non-terminal server error: treat as stream-terminal on client side
      // to prevent idle-timer double-fire of onError/onDone.
      failStream(String(event.content || "服务异常"));
      return;
    }

    if (eventType === "done") {
      doneReceived = true;
      clearIdleTimer();
      clearSlowTimer();
      if (cb.onFinal && !finalFired) {
        finalFired = true;
        cb.onFinal({
          type: "final",
          engine: "tutorbot",
          engine_session_id: chatId || sessionId,
          engine_turn_id: turnId,
          bot_id: botId,
        });
      }
      if (cb.onStatusEnd) cb.onStatusEnd();
      if (cb.onDone) cb.onDone();
      try {
        if (socketTask) socketTask.close({ code: 1000, reason: "done" });
      } catch (_) {}
    }
  }

  function connectTutorBotSocket() {
    if (aborted || doneReceived || !socketUrls.length) return;
    clearReconnectTimer();
    clearIdleTimer();
    resetIdleTimer();
    if (!firstTokenReceived) {
      startSlowTimer();
    }

    var socketUrl =
      socketUrls[Math.min(reconnectAttempts, socketUrls.length - 1)] ||
      socketUrls[0];
    connectedApiBase = socketUrlToApiBase(socketUrl);
    var headers = {
      "ngrok-skip-browser-warning": "true",
    };
    var freshToken = auth.getToken();
    if (freshToken) headers.Authorization = "Bearer " + freshToken;
    if (app && app.globalData && app.globalData.chatEngine) {
      headers["x-ai-engine"] = String(app.globalData.chatEngine || "").trim();
    }

    socketTask = wx.connectSocket({
      url: socketUrl,
      header: headers,
      timeout: 15000,
    });

    socketTask.onOpen(function () {
      if (aborted || doneReceived) return;
      socketOpen = true;
      reconnectAttempts = 0;
      resetIdleTimer();
      var payload = buildTurnSocketPayload(turnId, lastSeq);
      if (!payload) {
        failStream("启动流式会话失败");
        return;
      }
      emitTelemetry("ws_connected", { reconnect_attempts: reconnectAttempts });
      if (payload.type === "resume_from") {
        resumeAttempted = true;
        resumeSucceeded = false;
        emitTelemetry("resume_attempted", { seq: payload.seq || 0 });
      }
      socketTask.send({
        data: JSON.stringify(payload),
      });
      if (cancelRequested && turnId) {
        sendCancelTurn("user_cancel");
      }
    });

    socketTask.onMessage(function (res) {
      if (aborted || doneReceived) return;
      resetIdleTimer();
      var raw = typeof res.data === "string" ? res.data : "";
      if (!raw) return;
      try {
        handleEvent(JSON.parse(raw));
      } catch (_) {}
    });

    socketTask.onError(function (err) {
      if (!scheduleReconnect(err)) {
        failStream(err);
      }
    });

    socketTask.onClose(function (res) {
      socketOpen = false;
      if (aborted || doneReceived) return;
      if (!scheduleReconnect(res)) {
        failStream(res);
      }
    });
  }

  resetIdleTimer();
  startSlowTimer();

  var startTurnPayload = {
    query: query,
    conversation_id: sessionId,
    mode: mode,
  };
  if (clientTurnId) {
    startTurnPayload.client_turn_id = clientTurnId;
  }
  if (Array.isArray(opts && opts.tools) && opts.tools.length) {
    startTurnPayload.tools = opts.tools.slice();
  }
  if (opts && opts.config && typeof opts.config === "object") {
    startTurnPayload.config = opts.config;
  }
  if (opts && opts.interactionProfile) {
    startTurnPayload.interaction_profile = opts.interactionProfile;
  }
  if (
    opts &&
    opts.interactionHints &&
    typeof opts.interactionHints === "object"
  ) {
    startTurnPayload.interaction_hints = opts.interactionHints;
  }
  if (
    opts &&
    opts.followupQuestionContext &&
    typeof opts.followupQuestionContext === "object"
  ) {
    startTurnPayload.followup_question_context = opts.followupQuestionContext;
  }
  if (opts && opts.promptIntent && typeof opts.promptIntent === "object") {
    startTurnPayload.prompt_intent = opts.promptIntent;
  }
  if (opts && opts.persistUserMessage === false) {
    startTurnPayload.persist_user_message = false;
  }

  api
    .startChatTurn(startTurnPayload)
    .then(function (raw) {
      if (aborted) return;
      var payload = api.unwrapResponse(raw) || {};
      var stream = payload.stream || {};
      var bot = payload.bot || {};
      var conversation = payload.conversation || {};
      var preferredBase = endpoints.getPrimaryBaseUrl(false);
      botId = String(bot.id || "").trim();
      turnId = String(
        (stream.subscribe && stream.subscribe.turn_id) ||
          (payload.turn && payload.turn.id) ||
          "",
      ).trim();
      chatId = String(stream.chat_id || conversation.id || sessionId).trim();
      lastSeq = Number((stream.resume && stream.resume.seq) || 0) || 0;
      socketUrls = endpoints.getSocketUrlCandidates(
        stream.url || "/api/v1/ws",
        preferredBase,
      );
      if (!chatId || !turnId || !socketUrls.length) {
        throw new Error("启动流式会话失败");
      }
      if (
        cb.onUpdatedTitle &&
        conversation.title &&
        conversation.title !== "New conversation"
      ) {
        cb.onUpdatedTitle(conversation.title);
      } else if (cb.onUpdatedTitle && opts && opts.inferTitleOnStart) {
        var inferredTitle = inferConversationTitle(query);
        if (inferredTitle) cb.onUpdatedTitle(inferredTitle);
      }
      connectTutorBotSocket();
    })
    .catch(function (err) {
      clearIdleTimer();
      clearSlowTimer();
      if (aborted) return;
      if (cancelRequested) {
        if (cb.onDone) cb.onDone();
        return;
      }
      if (cb.onError) cb.onError(normalizeErrorMessage(err));
      if (cb.onDone) cb.onDone();
    });

  return function abort() {
    var shouldCancel = arguments[0] && arguments[0].cancelTurn;
    if (shouldCancel && !doneReceived) {
      cancelRequested = true;
      terminalWaitTicksAfterCancel = 0;
      clearSlowTimer();
      if (cb.onStatus) {
        cb.onStatus({
          type: "status",
          data: "cancelling",
          content: "正在停止本轮分析…",
          eventType: "cancelling",
          metadata: { visibility: "public" },
        });
      }
      if (socketOpen && socketTask && turnId) {
        resetIdleTimer();
        if (sendCancelTurn("user_cancel")) {
          return;
        }
      }
      return;
    }
    aborted = true;
    clearIdleTimer();
    clearSlowTimer();
    clearReconnectTimer();
    try {
      if (socketTask) socketTask.close({ code: 1000, reason: "abort" });
    } catch (_) {}
  };
}

module.exports = {
  streamChat: streamChat,
  buildStatusEvent: buildStatusEvent,
  buildPresentationEvent: buildPresentationEvent,
  buildTurnSocketPayload: buildTurnSocketPayload,
  computeReconnectDelayMs: computeReconnectDelayMs,
  inferConversationTitle: inferConversationTitle,
  normalizeErrorMessage: normalizeErrorMessage,
};
