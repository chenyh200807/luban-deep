// utils/sse-stream.js — wx.request + enableChunked SSE 流式引擎
// 直调主服务 POST /api/v1/stream/chat/sse，由后端统一分流到 Deeptutor
const auth = require("./auth");

/**
 * 流式 UTF-8 解码器
 * 用 TextDecoder({stream:true}) 保证跨 chunk 的多字节字符不会乱码
 */
var _streamDecoder = null;
function _getStreamDecoder() {
  if (!_streamDecoder && typeof TextDecoder !== "undefined") {
    _streamDecoder = new TextDecoder("utf-8", { stream: true });
  }
  return _streamDecoder;
}
function resetStreamDecoder() {
  _streamDecoder = null;
}

function arrayBufferToText(buffer) {
  var decoder = _getStreamDecoder();
  if (decoder) {
    return decoder.decode(buffer, { stream: true });
  }
  // 低版本降级：手动 UTF-8 解码
  const bytes = new Uint8Array(buffer);
  const parts = [];
  for (let i = 0; i < bytes.length; i += 4096) {
    parts.push(String.fromCharCode.apply(null, bytes.subarray(i, i + 4096)));
  }
  try {
    return decodeURIComponent(escape(parts.join("")));
  } catch (_) {
    return parts.join("");
  }
}

/**
 * SSE 事件解析器 — 按 \n\n 分割事件块，提取 data: 行
 * @param {string} buffer - 上一次未完成的缓冲
 * @param {string} chunk - 新到达的文本
 * @returns {{ rest: string, events: string[] }}
 */
function parseSSEEvents(buffer, chunk) {
  const merged = buffer + chunk;
  const blocks = merged.split(/\r?\n\r?\n/);
  const rest = blocks.pop() || "";
  const events = [];
  for (const block of blocks) {
    if (!block || !block.trim()) continue;
    const lines = block.split(/\r?\n/);
    const dataLines = [];
    for (const line of lines) {
      if (!line || line.startsWith(":")) continue;
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (dataLines.length) events.push(dataLines.join("\n"));
  }
  return { rest, events };
}

/**
 * SSE 流式聊天请求
 * @param {Object} opts
 * @param {string} opts.query      — 用户消息
 * @param {string} opts.sessionId  — 会话 ID
 * @param {string} [opts.userId]   — 用户 ID
 * @param {string} [opts.mode]     — AUTO / FAST / DEEP
 * @param {Object} [opts.structuredSubmitContext] — 结构化客观题提交上下文
 * @param {Object} callbacks
 * @param {Function} callbacks.onToken    — (text: string) => void
 * @param {Function} callbacks.onStatus   — (payload: object|string) => void
 * @param {Function} callbacks.onStatusEnd — () => void
 * @param {Function} callbacks.onDone     — () => void
 * @param {Function} callbacks.onFinal    — (data: object) => void
 * @param {Function} callbacks.onError    — (errMsg: string) => void
 * @param {Function} callbacks.onResult   — (data: object) => void
 * @param {Function} callbacks.onWorkflowStep     — (step) => void
 * @param {Function} callbacks.onWorkflowStepDone — (step) => void
 * @param {Function} callbacks.onThinkingHeader   — (payload: object|string) => void
 * @returns {Function} abort — 调用可中止请求
 */
function streamChat(opts, callbacks) {
  const { query, sessionId, userId, mode = "AUTO" } = opts;
  const cb = callbacks || {};

  const app = getApp();
  const baseUrl = app.globalData.apiUrl || "http://127.0.0.1:8001";
  const token = auth.getToken();

  if (!sessionId) {
    console.error("[SSE] Missing sessionId before streamChat", {
      queryPreview: (query || "").slice(0, 30),
    });
    if (cb.onError) cb.onError("会话初始化失败，请重试");
    if (cb.onDone) cb.onDone();
    return function () {};
  }

  var SSE_IDLE_TIMEOUT_MS = 60000; // 60s 无数据超时
  var _SLOW_RESPONSE_MS = 15000; // 15s 无 token 则提示弱网
  var sseBuffer = "";
  var aborted = false;
  var doneReceived = false;
  var _idleTimer = null; // 无数据超时定时器
  var _slowTimer = null; // 弱网软超时定时器
  var _firstTokenReceived = false; // 是否已收到首个 token
  resetStreamDecoder(); // 每次新请求重置，避免上次残留字节
  // [PRR-5.3.2] Retry state for transient network failures
  var _retryCount = 0;
  var _MAX_RETRIES = 3;
  var _RETRY_BASE_DELAY = 2000; // base delay for exponential backoff

  var chunkedSupported = true;

  function _resetIdleTimer() {
    if (_idleTimer) clearTimeout(_idleTimer);
    _idleTimer = setTimeout(function () {
      if (!aborted && !doneReceived) {
        console.warn(
          "[SSE] Idle timeout — no data for " + SSE_IDLE_TIMEOUT_MS + "ms",
        );
        if (cb.onError) cb.onError("响应超时，请重试");
        if (cb.onDone) cb.onDone();
        aborted = true;
        try {
          if (_currentTask) _currentTask.abort();
        } catch (_) {}
      }
    }, SSE_IDLE_TIMEOUT_MS);
  }

  function _clearIdleTimer() {
    if (_idleTimer) {
      clearTimeout(_idleTimer);
      _idleTimer = null;
    }
  }

  function _startSlowTimer() {
    _clearSlowTimer();
    _slowTimer = setTimeout(function () {
      if (!aborted && !doneReceived && !_firstTokenReceived) {
        if (cb.onStatus) cb.onStatus({ type: "status", data: "slow_response" });
      }
    }, _SLOW_RESPONSE_MS);
  }

  function _clearSlowTimer() {
    if (_slowTimer) {
      clearTimeout(_slowTimer);
      _slowTimer = null;
    }
  }

  function _doRequest() {
    _resetIdleTimer(); // 启动无数据超时
    _startSlowTimer(); // 启动弱网软超时
    var preferredEngine =
      app && app.globalData ? String(app.globalData.chatEngine || "").trim() : "";
    var requestHeaders = Object.assign(
      {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
        "x-client": "static_chat",
        "x-client-platform": "wechat_mp",
        "x-sse-format": "simple",
        "ngrok-skip-browser-warning": "true",
      },
      opts.clientTurnId ? { "X-Idempotency-Key": opts.clientTurnId } : {},
    );
    if (preferredEngine === "deeptutor" || preferredEngine === "legacy") {
      requestHeaders["x-ai-engine"] = preferredEngine;
    }
    var requestTask = wx.request({
      url: baseUrl + "/api/v1/stream/chat/sse",
      method: "POST",
      enableChunked: true,
      responseType: "text",
      dataType: "其他",
      header: requestHeaders,
      data: {
        user_id:
          userId ||
          auth.getUserId() ||
          (app.globalData && app.globalData.userId) ||
          "mp_anonymous",
        query,
        session_id: sessionId,
        conversation_id: sessionId,
        mode,
        tags: ["miniprogram", "wechat_mp"],
        structured_submit_context: opts.structuredSubmitContext,
      },
      success: function (res) {
        _clearIdleTimer();
        if (aborted) return;
        // HTTP 错误码处理
        if (res.statusCode === 401) {
          auth.clearToken();
          if (cb.onError) cb.onError("登录已过期，请重新登录");
          wx.redirectTo({ url: "/pages/login/login" });
          return;
        }
        if (res.statusCode >= 400) {
          if (cb.onError) cb.onError(`请求失败: HTTP ${res.statusCode}`);
          return;
        }
        // 降级模式：enableChunked 不可用时，一次性解析完整响应
        if (!chunkedSupported && res.data) {
          var rawText =
            typeof res.data === "string" ? res.data : JSON.stringify(res.data);
          var result = parseSSEEvents("", rawText + "\n\n");
          for (var i = 0; i < result.events.length; i++) {
            _handleEvent(result.events[i]);
          }
        }
        // chunked 模式：flush decoder 残留字节 + 处理 sseBuffer 残留事件
        if (chunkedSupported && sseBuffer) {
          // flush TextDecoder 内部缓冲
          var decoder = _getStreamDecoder();
          if (decoder) {
            var tail = decoder.decode(new Uint8Array(0), { stream: false });
            if (tail) sseBuffer += tail;
          }
          // 处理 sseBuffer 中最后一个未被 \n\n 终结的事件
          var finalResult = parseSSEEvents("", sseBuffer + "\n\n");
          for (var fi = 0; fi < finalResult.events.length; fi++) {
            _handleEvent(finalResult.events[fi]);
          }
          sseBuffer = "";
        }
        // 兜底触发 done
        if (!doneReceived && cb.onDone) cb.onDone();
      },
      fail: function (err) {
        _clearIdleTimer();
        if (aborted) return;
        if (err.errMsg && err.errMsg.includes("abort")) return;
        // enableChunked 模式下 401 可能走 fail 而不是 success
        // 检测到 404/401 时清 token 跳登录
        if (
          err.errMsg &&
          (err.errMsg.includes("404") || err.errMsg.includes("401"))
        ) {
          auth.clearToken();
          if (cb.onError) cb.onError("登录已过期，请重新登录");
          wx.redirectTo({ url: "/pages/login/login" });
          return;
        }
        // [PRR-5.3.2] Retry on transient network failure with exponential backoff
        if (_retryCount < _MAX_RETRIES && !doneReceived) {
          _retryCount++;
          sseBuffer = ""; // [PRR-CR7] Reset stale buffer before retry
          var delay = _RETRY_BASE_DELAY * Math.pow(2, _retryCount - 1);
          wx.showToast({
            title: "网络中断，第" + _retryCount + "次重连中…",
            icon: "none",
            duration: delay,
          });
          setTimeout(function () {
            if (!aborted) _currentTask = _doRequest(); // [PRR-CR7] Update task ref for abort()
          }, delay);
          return;
        }
        if (cb.onError) cb.onError(err.errMsg || "网络请求失败，请重试");
      },
    });

    // onChunkReceived 可能在某些环境不可用（模拟器/旧基础库）
    if (requestTask && typeof requestTask.onChunkReceived === "function") {
      requestTask.onChunkReceived(function (res) {
        if (aborted) return;
        _resetIdleTimer(); // 收到数据，重置超时
        var text = arrayBufferToText(res.data);
        var result = parseSSEEvents(sseBuffer, text);
        sseBuffer = result.rest;
        for (var i = 0; i < result.events.length; i++) {
          if (aborted) break;
          _handleEvent(result.events[i]);
        }
      });
    } else {
      // enableChunked 不可用，标记降级模式
      chunkedSupported = false;
      console.warn("[SSE] enableChunked 不可用，使用降级模式（非流式）");
    }
    return requestTask;
  } // end _doRequest

  // [PRR-5.3.2] Initial call
  let _currentTask = _doRequest();

  function _handleEvent(data) {
    // [DONE] — 流式结束
    if (data === "[DONE]") {
      doneReceived = true;
      if (cb.onDone) cb.onDone();
      return;
    }
    // [ERROR] — 业务错误
    if (data.startsWith("[ERROR]")) {
      if (cb.onError) cb.onError(data.slice(8));
      return;
    }

    let parsed;
    try {
      parsed = JSON.parse(data);
    } catch (_) {
      // 纯文本 token
      if (!_firstTokenReceived) {
        _firstTokenReceived = true;
        _clearSlowTimer();
      }
      if (cb.onToken) cb.onToken(data);
      return;
    }

    if (!parsed || typeof parsed !== "object") {
      if (!_firstTokenReceived) {
        _firstTokenReceived = true;
        _clearSlowTimer();
      }
      if (cb.onToken) cb.onToken(String(parsed));
      return;
    }

    // [FIX 2026-04-01] 服务端在流式 chunk 中附带 updated_title 字段
    // 用于实时更新会话标题（替代"新对话"占位符）
    if (parsed.updated_title && cb.onUpdatedTitle) {
      cb.onUpdatedTitle(parsed.updated_title);
    }

    switch (parsed.type) {
      case "token":
        if (!_firstTokenReceived) {
          _firstTokenReceived = true;
          _clearSlowTimer();
        }
        if (typeof parsed.data === "string" && cb.onToken)
          cb.onToken(parsed.data);
        break;
      case "status":
        if (cb.onStatus) cb.onStatus(parsed);
        break;
      case "status_end":
        if (cb.onStatusEnd) cb.onStatusEnd();
        break;
      case "thinking_header":
        if (cb.onThinkingHeader) cb.onThinkingHeader(parsed);
        break;
      case "workflow_step":
        if (cb.onWorkflowStep) cb.onWorkflowStep(parsed);
        break;
      case "workflow_step_done":
        if (cb.onWorkflowStepDone) cb.onWorkflowStepDone(parsed);
        break;
      case "meta":
        // message_id 等元信息 — 小程序暂不需要
        break;
      case "final":
        if (cb.onFinal) cb.onFinal(parsed);
        break;
      case "result":
        if (cb.onResult) cb.onResult(parsed);
        break;
      case "error":
        if (cb.onError) cb.onError(parsed.data || parsed.message || "服务异常");
        break;
      case "answer_start":
      case "replay_reset":
        break;
      case "mcq_interactive":
        // 将后端结构化 MCQ 事件转发给 chat.js 处理
        // 后端 _should_emit_mcq_interactive() 已做 intent 过滤
        // 只有 Practice/Targeted_Practice 才会发此事件
        if (cb.onMcqInteractive) cb.onMcqInteractive(parsed);
        break;
      default:
        break;
    }
  }

  return function abort() {
    aborted = true;
    _clearIdleTimer();
    _clearSlowTimer();
    try {
      if (_currentTask) _currentTask.abort();
    } catch (_) {}
  };
}

module.exports = {
  streamChat,
  parseSSEEvents,
  arrayBufferToText,
  resetStreamDecoder,
};
