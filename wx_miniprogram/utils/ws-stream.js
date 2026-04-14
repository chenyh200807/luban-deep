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
  var idleTimeoutMs = 60000;
  var slowResponseMs = 15000;
  var botId = "";
  var chatId = sessionId;
  var socketUrls = [];

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

  function failStream(err) {
    if (aborted || doneReceived) return;
    aborted = true;
    clearIdleTimer();
    clearSlowTimer();
    if (cb.onError) cb.onError(normalizeErrorMessage(err));
    if (cb.onDone) cb.onDone();
    try {
      if (socketTask) socketTask.close({ code: 1000, reason: "abort" });
    } catch (_) {}
  }

  function handleEvent(event) {
    if (!event || typeof event !== "object") return;
    var eventType = String(event.type || "").trim();
    var eventMetadata = event.metadata || {};

    if (eventType === "content") {
      if (!firstTokenReceived) {
        firstTokenReceived = true;
        clearSlowTimer();
      }
      if (cb.onToken) cb.onToken(String(event.content || ""));
      return;
    }

    if (eventType === "thinking" || eventType === "progress") {
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

    if (eventType === "error") {
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
          engine_turn_id: "",
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
    clearIdleTimer();
    resetIdleTimer();

    var socketUrl = socketUrls[0];
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
      resetIdleTimer();
      socketTask.send({
        data: JSON.stringify({
          content: query,
          chat_id: chatId || sessionId,
          mode: mode,
        }),
      });
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
      failStream(err);
    });

    socketTask.onClose(function (res) {
      failStream(res);
    });
  }

  resetIdleTimer();
  startSlowTimer();

  api
    .startChatTurn({
      query: query,
      conversation_id: sessionId,
      mode: mode,
    })
    .then(function (raw) {
      if (aborted) return;
      var payload = api.unwrapResponse(raw) || {};
      var stream = payload.stream || {};
      var bot = payload.bot || {};
      var conversation = payload.conversation || {};
      var preferredBase = endpoints.getPrimaryBaseUrl(false);
      botId = String(bot.id || "").trim();
      chatId = String(stream.chat_id || conversation.id || sessionId).trim();
      socketUrls = endpoints.getSocketUrlCandidates(
        stream.url || "/api/v1/mobile/tutorbot/ws/construction-exam-coach",
        preferredBase,
      );
      if (!chatId || !socketUrls.length) {
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
