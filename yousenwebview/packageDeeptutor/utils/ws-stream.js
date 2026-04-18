// utils/ws-stream.js — start-turn + /api/v1/ws 流式引擎
const auth = require("./auth");
const api = require("./api");
const endpoints = require("./endpoints");
const hostRuntime = require("./host-runtime");

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

function resolveEventVisibility(event) {
  if (!event || typeof event !== "object") return "public";
  var direct = String(event.visibility || "").trim().toLowerCase();
  if (direct === "internal") return "internal";
  var metadata = event.metadata || {};
  var nested = String(metadata.visibility || "").trim().toLowerCase();
  return nested === "internal" ? "internal" : "public";
}

var RECONNECT_BASE_DELAY_MS = 400;
var RECONNECT_MAX_DELAY_MS = 4000;
var RECONNECT_MAX_ATTEMPTS = 5;

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

function streamChat(opts, callbacks) {
  var cb = callbacks || {};
  var query = String((opts && opts.query) || "").trim();
  var sessionId = String((opts && opts.sessionId) || "").trim();
  var mode = String((opts && opts.mode) || "AUTO").trim().toUpperCase();

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

  var token = auth.getToken();
  var aborted = false;
  var doneReceived = false;
  var firstTokenReceived = false;
  var idleTimer = null;
  var slowTimer = null;
  var reconnectTimer = null;
  var socketTask = null;
  var idleTimeoutMs = 60000;
  var slowResponseMs = 15000;
  var botId = "";
  var chatId = sessionId;
  var turnId = "";
  var lastSeq = 0;
  var socketUrls = [];
  var reconnectAttempts = 0;
  var socketOpen = false;
  var cancelRequested = false;

  function clearIdleTimer() {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
  }

  function resetIdleTimer() {
    clearIdleTimer();
    idleTimer = setTimeout(function () {
      if (!aborted && !doneReceived) {
        if (cb.onError) cb.onError("响应超时，请重试");
        if (cb.onDone) cb.onDone();
        aborted = true;
        try {
          if (socketTask) socketTask.close({ code: 1000, reason: "idle_timeout" });
        } catch (_) {}
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

  function normalizeErrorMessage(err) {
    if (!err) return "连接失败，请重试";
    if (typeof err === "string") return err;
    return err.errMsg || err.message || "连接失败，请重试";
  }

  function failStream(err) {
    if (aborted || doneReceived) return;
    aborted = true;
    clearIdleTimer();
    clearSlowTimer();
    clearReconnectTimer();
    if (cb.onError) cb.onError(normalizeErrorMessage(err));
    if (cb.onDone) cb.onDone();
    try {
      if (socketTask) socketTask.close({ code: 1000, reason: "abort" });
    } catch (_) {}
  }

  function scheduleReconnect(err) {
    if (aborted || doneReceived || reconnectTimer || !socketUrls.length) return false;
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
      return;
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

    if (eventType === "thinking" || eventType === "progress") {
      if (visibility !== "public") {
        return;
      }
      if (cb.onStatus) {
        cb.onStatus({
          type: "status",
          data: event.content || eventType,
          content: event.content || "",
          source: event.source || "",
          stage: "",
          eventType: eventType,
          metadata: eventMetadata,
          seq: 0,
        });
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
        return;
      }
      return;
    }

    if (eventType === "error") {
      if (eventMetadata && eventMetadata.status === "cancelled") {
        return;
      }
      if (eventMetadata && eventMetadata.turn_terminal) {
        failStream(String(event.content || "服务异常"));
        return;
      }
      if (cb.onError) cb.onError(String(event.content || "服务异常"));
      return;
    }

    if (eventType === "done") {
      doneReceived = true;
      clearIdleTimer();
      clearSlowTimer();
      if (cb.onFinal) {
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

    var socketUrl = socketUrls[Math.min(reconnectAttempts, socketUrls.length - 1)] || socketUrls[0];
    var headers = {
      "ngrok-skip-browser-warning": "true",
    };
    if (token) headers.Authorization = "Bearer " + token;
    var chatEngine = hostRuntime.getChatEngine();
    if (chatEngine) {
      headers["x-ai-engine"] = chatEngine;
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
      socketTask.send({
        data: JSON.stringify(payload),
      });
      if (cancelRequested && turnId) {
        socketTask.send({
          data: JSON.stringify({
            type: "cancel_turn",
            turn_id: turnId,
          }),
        });
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
  if (Array.isArray(opts && opts.tools) && opts.tools.length) {
    startTurnPayload.tools = opts.tools.slice();
  }
  if (opts && opts.interactionProfile) {
    startTurnPayload.interaction_profile = opts.interactionProfile;
  }
  if (opts && opts.interactionHints && typeof opts.interactionHints === "object") {
    startTurnPayload.interaction_hints = opts.interactionHints;
  }
  if (
    opts &&
    opts.followupQuestionContext &&
    typeof opts.followupQuestionContext === "object"
  ) {
    startTurnPayload.followup_question_context = opts.followupQuestionContext;
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
      turnId = String((stream.subscribe && stream.subscribe.turn_id) || (payload.turn && payload.turn.id) || "").trim();
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
      if (cb.onError) cb.onError(normalizeErrorMessage(err));
      if (cb.onDone) cb.onDone();
    });

  return function abort() {
    var shouldCancel = arguments[0] && arguments[0].cancelTurn;
    if (shouldCancel && !doneReceived) {
      cancelRequested = true;
      clearSlowTimer();
      if (socketOpen && socketTask && turnId) {
        resetIdleTimer();
        try {
          socketTask.send({
            data: JSON.stringify({
              type: "cancel_turn",
              turn_id: turnId,
            }),
          });
          return;
        } catch (_) {}
      }
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
  buildPresentationEvent: buildPresentationEvent,
  buildTurnSocketPayload: buildTurnSocketPayload,
  computeReconnectDelayMs: computeReconnectDelayMs,
  inferConversationTitle: inferConversationTitle,
};
