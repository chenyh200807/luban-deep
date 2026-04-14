// utils/ws-stream.js — start-turn + /api/v1/ws 流式引擎
const auth = require("./auth");
const api = require("./api");
const endpoints = require("./endpoints");

function inferConversationTitle(query) {
  var text = String(query || "").trim();
  if (!text) return "";
  return text.length > 50 ? text.slice(0, 50) + "..." : text;
}

function buildMcqInteractiveEvent(resultMetadata) {
  var summary = resultMetadata && resultMetadata.summary;
  var results = summary && Array.isArray(summary.results) ? summary.results : [];
  var questions = [];
  var hiddenContexts = [];

  for (var i = 0; i < results.length; i++) {
    var item = results[i];
    var qaPair = item && item.qa_pair;
    if (!qaPair || typeof qaPair !== "object") continue;
    var questionType = String(qaPair.question_type || "").trim().toLowerCase();
    var rawOptions = qaPair.options;
    if (questionType !== "choice" || !rawOptions || typeof rawOptions !== "object") {
      continue;
    }
    var optionKeys = Object.keys(rawOptions).sort();
    if (!optionKeys.length) continue;

    var options = [];
    var optionMap = {};
    for (var j = 0; j < optionKeys.length; j++) {
      var key = String(optionKeys[j] || "").trim().toUpperCase();
      var value = String(rawOptions[optionKeys[j]] || "").trim();
      if (!key || !value) continue;
      options.push({ key: key, text: value });
      optionMap[key] = value;
    }
    if (!options.length) continue;

    var index = questions.length + 1;
    questions.push({
      index: index,
      stem: String(qaPair.question || "").trim(),
      question_type:
        String(qaPair.correct_answer || "").trim().length > 1
          ? "multi_choice"
          : "single_choice",
      options: options,
    });
    hiddenContexts.push({
      question_id: String(qaPair.question_id || "q_" + index).trim(),
      question: String(qaPair.question || "").trim(),
      question_type: "choice",
      options: optionMap,
      correct_answer: String(qaPair.correct_answer || "").trim(),
      explanation: String(qaPair.explanation || "").trim(),
      difficulty: String(qaPair.difficulty || "").trim(),
      concentration: String(
        qaPair.concentration || qaPair.knowledge_point || qaPair.topic || "",
      ).trim(),
      knowledge_context: String(
        qaPair.knowledge_context || qaPair.explanation || "",
      ).trim(),
    });
  }

  if (!questions.length) return null;
  return {
    type: "mcq_interactive",
    questions: questions,
    hidden_contexts: hiddenContexts,
    submit_hint:
      questions.length > 1 ? "多题作答，先分别点选，再提交答案。" : "请选择后提交答案",
    receipt: "",
  };
}

function streamChat(opts, callbacks) {
  var cb = callbacks || {};
  var query = String((opts && opts.query) || "").trim();
  var sessionId = String((opts && opts.sessionId) || "").trim();
  var mode = String((opts && opts.mode) || "AUTO").trim().toUpperCase();
  var tools = Array.isArray(opts && opts.tools) ? opts.tools : [];
  var interactionProfile = String(
    (opts && opts.interactionProfile) || "mini_tutor",
  ).trim();
  var interactionHints =
    opts && opts.interactionHints && typeof opts.interactionHints === "object"
      ? opts.interactionHints
      : null;

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
  var token = auth.getToken();
  var aborted = false;
  var doneReceived = false;
  var firstTokenReceived = false;
  var idleTimer = null;
  var slowTimer = null;
  var socketTask = null;
  var reconnectCount = 0;
  var maxReconnects = 3;
  var retryBaseDelay = 2000;
  var reconnectScheduled = false;
  var idleTimeoutMs = 60000;
  var slowResponseMs = 15000;
  var lastSeq = 0;
  var turnId = "";
  var socketUrls = [];
  var socketUrlIndex = 0;

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

  function handleEvent(event) {
    if (!event || typeof event !== "object") return;
    lastSeq = Math.max(lastSeq, Number(event.seq || 0));
    var eventType = String(event.type || "").trim();
    var eventMetadata = event.metadata || {};

    if (eventType === "session") return;

    if (eventType === "content") {
      if (!firstTokenReceived) {
        firstTokenReceived = true;
        clearSlowTimer();
      }
      if (cb.onToken) cb.onToken(String(event.content || ""));
      return;
    }

    if (
      eventType === "stage_start" ||
      eventType === "thinking" ||
      eventType === "progress" ||
      eventType === "observation" ||
      eventType === "tool_call" ||
      eventType === "tool_result"
    ) {
      if (cb.onStatus) {
        cb.onStatus({
          type: "status",
          data: event.content || event.stage || eventType,
          content: event.content || "",
          source: event.source || "",
          stage: event.stage || "",
          eventType: eventType,
          metadata: eventMetadata,
          seq: Number(event.seq || 0),
        });
      }
      return;
    }

    if (eventType === "sources") {
      if (cb.onFinal) {
        cb.onFinal({
          type: "final",
          engine: "deeptutor",
          engine_session_id: event.session_id || sessionId,
          engine_turn_id: event.turn_id || turnId,
          citations: eventMetadata.sources || eventMetadata || {},
        });
      }
      return;
    }

    if (eventType === "result") {
      var mcqEvent = buildMcqInteractiveEvent(eventMetadata);
      if (mcqEvent && cb.onMcqInteractive) cb.onMcqInteractive(mcqEvent);
      if (cb.onFinal) {
        cb.onFinal({
          type: "final",
          engine: "deeptutor",
          engine_session_id: event.session_id || sessionId,
          engine_turn_id: event.turn_id || turnId,
        });
      }
      if (cb.onResult) cb.onResult(eventMetadata);
      return;
    }

    if (eventType === "error") {
      if (cb.onError) cb.onError(String(event.content || "服务异常"));
      return;
    }

    if (eventType === "done") {
      doneReceived = true;
      clearIdleTimer();
      clearSlowTimer();
      if (cb.onStatusEnd) cb.onStatusEnd();
      if (cb.onDone) cb.onDone();
    }
  }

  function scheduleReconnect(reason) {
    if (aborted || doneReceived) return;
    if (reconnectScheduled) return;
    if (reconnectCount >= maxReconnects) {
      if (cb.onError) cb.onError(reason || "连接中断，请重试");
      if (cb.onDone) cb.onDone();
      return;
    }
    reconnectScheduled = true;
    reconnectCount += 1;
    socketUrlIndex = (socketUrlIndex + 1) % Math.max(socketUrls.length, 1);
    var delay = retryBaseDelay * Math.pow(2, reconnectCount - 1);
    wx.showToast({
      title: "网络中断，第" + reconnectCount + "次重连中…",
      icon: "none",
      duration: delay,
    });
    setTimeout(function () {
      reconnectScheduled = false;
      if (!aborted && !doneReceived) {
        connectSocketAndSubscribe(true);
      }
    }, delay);
  }

  function connectSocketAndSubscribe(isResume) {
    if (aborted || doneReceived || !turnId) return;
    clearIdleTimer();
    resetIdleTimer();

    var socketUrl = socketUrls[socketUrlIndex];
    var headers = {
      "ngrok-skip-browser-warning": "true",
    };
    if (token) headers.Authorization = "Bearer " + token;
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
      reconnectScheduled = false;
      resetIdleTimer();
      var subscribePayload = isResume
        ? { type: "resume_from", turn_id: turnId, seq: lastSeq }
        : { type: "subscribe_turn", turn_id: turnId, after_seq: 0 };
      socketTask.send({ data: JSON.stringify(subscribePayload) });
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
      if (aborted || doneReceived) return;
      scheduleReconnect(normalizeErrorMessage(err));
    });

    socketTask.onClose(function (res) {
      if (aborted || doneReceived) return;
      if (res && (res.code === 1000 || res.code === 1005) && doneReceived) return;
      scheduleReconnect(normalizeErrorMessage(res));
    });
  }

  resetIdleTimer();
  startSlowTimer();

  api
    .startChatTurn({
      query: query,
      conversation_id: sessionId,
      mode: mode,
      language: "zh",
      tools: tools,
      interaction_profile: interactionProfile,
      interaction_hints: interactionHints,
      followup_question_context:
        opts && opts.followupQuestionContext ? opts.followupQuestionContext : null,
    })
    .then(function (raw) {
      if (aborted) return;
      var payload = api.unwrapResponse(raw) || {};
      var stream = payload.stream || {};
      var conversation = payload.conversation || {};
      var preferredBase = endpoints.getPrimaryBaseUrl(false);
      turnId = String((payload.turn && payload.turn.id) || "").trim();
      socketUrls = endpoints.getSocketUrlCandidates(
        stream.url || "/api/v1/ws",
        preferredBase,
      );
      socketUrlIndex = 0;
      if (!turnId || !socketUrls.length) {
        throw new Error("启动流式会话失败");
      }
      if (cb.onUpdatedTitle && conversation.title && conversation.title !== "New conversation") {
        cb.onUpdatedTitle(conversation.title);
      } else if (cb.onUpdatedTitle && opts && opts.inferTitleOnStart) {
        var inferredTitle = inferConversationTitle(query);
        if (inferredTitle) cb.onUpdatedTitle(inferredTitle);
      }
      connectSocketAndSubscribe(false);
    })
    .catch(function (err) {
      clearIdleTimer();
      clearSlowTimer();
      if (aborted) return;
      if (cb.onError) cb.onError(normalizeErrorMessage(err));
      if (cb.onDone) cb.onDone();
    });

  return function abort() {
    aborted = true;
    clearIdleTimer();
    clearSlowTimer();
    try {
      if (socketTask) socketTask.close({ code: 1000, reason: "abort" });
    } catch (_) {}
  };
}

module.exports = {
  streamChat: streamChat,
  buildMcqInteractiveEvent: buildMcqInteractiveEvent,
  inferConversationTitle: inferConversationTitle,
};
