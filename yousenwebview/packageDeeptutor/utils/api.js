// utils/api.js — Gateway / 主服务 HTTP 请求封装
const auth = require("./auth");
const endpoints = require("./endpoints");
const runtime = require("./runtime");

// ── 常量 ──────────────────────────────────────────────────
var MAX_RETRIES = 2; // 最大重试次数
var RETRY_BASE_DELAY = 1000; // 首次重试延迟 ms
var REQUEST_TIMEOUT = 15000; // 请求超时 ms
var RETRYABLE_METHODS = { GET: true, PUT: true, DELETE: true }; // 幂等方法才重试
var IN_FLIGHT_REQUESTS = Object.create(null);
var TOKEN_REFRESH_MARGIN_SECONDS = 60 * 60 * 24; // 仅在 token 临期 24 小时内续期
var IN_FLIGHT_REFRESH = null;

function relaunchLogin() {
  runtime.redirectToLogin();
}

function getBaseUrl(useGateway) {
  return endpoints.getPrimaryBaseUrl(useGateway !== false);
}

/**
 * 解包 API 响应 — 统一 resp.data || resp 的处理
 * 后端可能返回 { data: {...} } 或直接 {...}
 */
/** 从错误响应提取结构化错误码: detail 兼容对象(新后端)与 "{'error': 'x'}"
 * 字符串(旧后端 str()化)。取不到=空串(调用方按网络类处理)。 */
function errorCodeOf(error) {
  var detail = error && error.payload && error.payload.detail;
  if (detail && typeof detail === "object") return String(detail.error || "");
  var text = String(detail || "");
  var m = text.match(/'error':\s*'([a-z0-9_]+)'/i) || text.match(/"error":\s*"([a-z0-9_]+)"/i);
  return m ? m[1] : "";
}

function unwrapResponse(raw) {
  if (!raw || typeof raw !== "object") return raw;
  // 如果有 data 字段且不是基础类型列表（排除 {data: "string"} 的情况）
  if (raw.data !== undefined && typeof raw.data === "object") return raw.data;
  return raw;
}

function parseHttpError(message) {
  var match = /^HTTP_(\d+)(?::\s*(.*))?$/.exec(String(message || ""));
  if (!match) {
    return { status: 0, payload: null, detailText: "" };
  }
  var payloadText = String(match[2] || "").trim();
  var payload = null;
  var detailText = payloadText;
  if (payloadText) {
    try {
      payload = JSON.parse(payloadText);
      if (
        payload &&
        typeof payload === "object" &&
        payload.detail !== undefined
      ) {
        detailText = String(payload.detail || "").trim() || payloadText;
      }
    } catch (_err) {}
  }
  return {
    status: parseInt(match[1], 10) || 0,
    payload: payload,
    detailText: detailText,
  };
}

function createHttpError(statusCode, payload) {
  var status = Number(statusCode) || 0;
  var suffix = "";
  if (payload !== undefined) {
    try {
      suffix = ": " + JSON.stringify(payload);
    } catch (_err) {
      suffix = "";
    }
  }
  var err = new Error("HTTP_" + status + suffix);
  err.statusCode = status;
  err.payload = payload || null;
  return err;
}

function inspectRequestError(err) {
  var message = String((err && err.message) || "");
  var lowered = message.toLowerCase();
  var http = parseHttpError(message);
  var detailText = http.detailText || message;
  return {
    rawMessage: message,
    loweredMessage: lowered,
    status: http.status,
    payload: http.payload,
    detailText: String(detailText || "").trim(),
    isAuthExpired: message === "AUTH_EXPIRED",
    isNetworkError: message.indexOf("NETWORK_ERROR:") === 0,
    isTimeout:
      lowered.indexOf("timeout") >= 0 ||
      lowered.indexOf("timed out") >= 0 ||
      lowered.indexOf("超时") >= 0,
  };
}

function shouldRetryWechatLogin(err) {
  var info = inspectRequestError(err);
  if (info.isNetworkError) {
    return true;
  }
  if (info.status >= 500 && info.status < 600) {
    return true;
  }
  if (info.detailText) {
    var lowered = info.detailText.toLowerCase();
    if (
      lowered.indexOf("code2session") >= 0 ||
      lowered.indexOf("stable_token") >= 0 ||
      lowered.indexOf("request timed out") >= 0
    ) {
      return true;
    }
  }
  return false;
}

function describeRequestError(err, fallbackMsg, opts) {
  var options = opts || {};
  var info = inspectRequestError(err);
  var customMap = options.customMap;
  if (typeof customMap === "function") {
    var customMsg = customMap(info);
    if (customMsg) {
      return customMsg;
    }
  }
  if (info.isAuthExpired) {
    return "登录已失效，请重新登录";
  }
  if (info.status === 429) {
    return "操作过于频繁，请稍后再试";
  }
  if (info.isTimeout) {
    if (options.context === "wechat_login") {
      return "快速登录服务响应超时，请稍后重试";
    }
    return "请求超时，请稍后重试";
  }
  if (info.isNetworkError) {
    return "连接服务器失败，请检查网络后重试";
  }
  if (info.status >= 500) {
    if (options.context === "wechat_login") {
      if (info.detailText.toLowerCase().indexOf("getuserphonenumber") >= 0) {
        return "手机号验证服务暂时不可用，请稍后重试";
      }
      return "快速登录服务暂时不稳定，请稍后重试";
    }
    return "服务暂时不可用，请稍后重试";
  }
  if (info.detailText && !/^HTTP_\d+:/.test(info.rawMessage)) {
    return info.detailText;
  }
  return fallbackMsg;
}

function requestStateGet(url, opts) {
  return request(
    Object.assign(
      {
        url: url,
        method: "GET",
        dedupeInFlight: true,
        noRetry: true,
      },
      opts || {},
    ),
  );
}

function applyAuthPayload(payload) {
  var body = unwrapResponse(payload);
  if (!body || typeof body !== "object" || !body.token) {
    return null;
  }
  auth.setToken(body.token, body.expires_at, body);
  return body.token;
}

function refreshAuthToken(opts) {
  var token = auth.getToken();
  var refreshOpts = Object.assign({}, opts || {});
  if (!token) {
    return Promise.reject(new Error("AUTH_EXPIRED"));
  }
  if (IN_FLIGHT_REFRESH) {
    return IN_FLIGHT_REFRESH;
  }
  IN_FLIGHT_REFRESH = new Promise(function (resolve, reject) {
    rawRequest({
      url: "/api/v1/auth/refresh",
      method: "POST",
      useGateway: refreshOpts.useGateway,
      baseUrl: refreshOpts.baseUrl,
      _baseCandidates: refreshOpts._baseCandidates,
      skipAuthRefresh: true,
      dedupeInFlight: true,
      noRetry: true,
    })
      .then(function (resp) {
        var refreshedToken = applyAuthPayload(resp);
        if (!refreshedToken) {
          auth.clearToken();
          relaunchLogin();
          reject(new Error("AUTH_EXPIRED"));
          return;
        }
        resolve(refreshedToken);
      })
      .catch(function (_err) {
        auth.clearToken();
        relaunchLogin();
        reject(new Error("AUTH_EXPIRED"));
      })
      .then(
        function () {
          IN_FLIGHT_REFRESH = null;
        },
        function () {
          IN_FLIGHT_REFRESH = null;
        },
      );
  });
  return IN_FLIGHT_REFRESH;
}

function ensureFreshAuthToken(opts) {
  var token = auth.getToken();
  if (!token) {
    return Promise.reject(new Error("AUTH_EXPIRED"));
  }
  if (
    typeof auth.shouldRefreshToken === "function" &&
    auth.shouldRefreshToken(TOKEN_REFRESH_MARGIN_SECONDS)
  ) {
    return refreshAuthToken(opts).then(function (refreshedToken) {
      return refreshedToken || auth.getToken() || "";
    });
  }
  return Promise.resolve(token);
}

/**
 * 通用请求（带 token 自动注入 + 指数退避重试 + Token 刷新）
 * @param {object} opts - { url, method, data, useGateway, noAuth, _retryCount }
 */
function request(opts) {
  var requestOptions = Object.assign({}, opts || {});
  if (
    !requestOptions.noAuth &&
    !requestOptions.skipAuthRefresh &&
    auth.getToken() &&
    typeof auth.shouldRefreshToken === "function" &&
    auth.shouldRefreshToken(TOKEN_REFRESH_MARGIN_SECONDS)
  ) {
    return ensureFreshAuthToken(requestOptions).then(function () {
      return rawRequest(requestOptions);
    });
  }
  return rawRequest(requestOptions);
}

function rawRequest(opts) {
  var method = opts.method || "GET";
  var data = opts.data || {};
  var useGateway = opts.useGateway || false;
  var noAuth = opts.noAuth || false;
  var retryCount = opts._retryCount || 0;
  var baseIndex = opts._baseIndex || 0;
  var baseCandidates =
    opts._baseCandidates ||
    endpoints.getBaseUrlCandidates(useGateway, opts.baseUrl);

  var baseUrl = baseCandidates[baseIndex] || getBaseUrl(useGateway);
  var fullUrl = opts.url.startsWith("http") ? opts.url : baseUrl + opts.url;
  var token = auth.getToken();
  var inFlightKey =
    method === "GET" && opts.dedupeInFlight
      ? [method, fullUrl, noAuth ? "" : token || ""].join("::")
      : "";

  var header = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
  };
  if (!noAuth && token) {
    header["Authorization"] = "Bearer " + token;
  }

  if (inFlightKey && IN_FLIGHT_REQUESTS[inFlightKey]) {
    return IN_FLIGHT_REQUESTS[inFlightKey];
  }

  var pendingPromise = new Promise(function (resolve, reject) {
    wx.request({
      url: fullUrl,
      method: method,
      data: data,
      header: header,
      timeout: REQUEST_TIMEOUT,
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          if (!opts.url.startsWith("http")) {
            endpoints.rememberWorkingBaseUrl(baseUrl, useGateway);
          }
          resolve(res.data);
          return;
        }

        if (res.statusCode === 401) {
          if (noAuth) {
            // noAuth 401: reject with a sanitized opaque error so the raw backend payload
            // (e.g. {"detail":"用户名或密码错误"}) is never embedded in the error message
            // string visible to UI layers. statusCode and payload are available on the
            // error object for programmatic inspection only. (2026-06-12 security fix)
            var noAuthErr = new Error("HTTP_401");
            noAuthErr.statusCode = 401;
            noAuthErr.payload = res.data || null;
            reject(noAuthErr);
            return;
          }
          if (opts.suppressAuthRedirect) {
            auth.clearToken();
            reject(new Error("AUTH_EXPIRED"));
            return;
          }
          if (opts.skipAuthRefresh) {
            reject(new Error("AUTH_EXPIRED"));
            return;
          }
          // Token 过期 — 清除并跳转登录
          auth.clearToken();
          relaunchLogin();
          reject(new Error("AUTH_EXPIRED"));
          return;
        }

        if (
          !opts.noBaseFallback &&
          !opts.url.startsWith("http") &&
          res.statusCode >= 500 &&
          baseIndex + 1 < baseCandidates.length
        ) {
          var nextBaseOnServerError = baseCandidates[baseIndex + 1];
          console.warn(
            "[API] " +
              res.statusCode +
              " on " +
              fullUrl +
              ", fallback to " +
              nextBaseOnServerError,
          );
          request(
            Object.assign({}, opts, {
              _baseCandidates: baseCandidates,
              _baseIndex: baseIndex + 1,
            }),
          )
            .then(resolve)
            .catch(reject);
          return;
        }

        if (res.statusCode === 503) {
          reject(createHttpError(503, res.data));
          return;
        }

        // 5xx 服务端错误 — 可重试
        if (
          res.statusCode >= 500 &&
          !opts.noRetry &&
          RETRYABLE_METHODS[method] &&
          retryCount < MAX_RETRIES
        ) {
          var delay = RETRY_BASE_DELAY * Math.pow(2, retryCount);
          console.warn(
            "[API] " +
              res.statusCode +
              " on " +
              fullUrl +
              ", retry " +
              (retryCount + 1) +
              "/" +
              MAX_RETRIES +
              " in " +
              delay +
              "ms",
          );
          setTimeout(function () {
            request(Object.assign({}, opts, { _retryCount: retryCount + 1 }))
              .then(resolve)
              .catch(reject);
          }, delay);
          return;
        }

        reject(createHttpError(res.statusCode, res.data));
      },
      fail: function (err) {
        if (err.errMsg && err.errMsg.includes("abort")) {
          reject(new Error("REQUEST_ABORTED"));
          return;
        }

        if (
          !opts.noBaseFallback &&
          !opts.url.startsWith("http") &&
          baseIndex + 1 < baseCandidates.length
        ) {
          var nextBase = baseCandidates[baseIndex + 1];
          console.warn("[API] Fallback to alternate base: " + nextBase);
          request(
            Object.assign({}, opts, {
              _baseCandidates: baseCandidates,
              _baseIndex: baseIndex + 1,
            }),
          )
            .then(resolve)
            .catch(reject);
          return;
        }

        // 网络错误 — 幂等请求可重试
        if (RETRYABLE_METHODS[method] && retryCount < MAX_RETRIES) {
          if (opts.noRetry) {
            reject(new Error("NETWORK_ERROR: " + (err.errMsg || "unknown")));
            return;
          }
          var delay = RETRY_BASE_DELAY * Math.pow(2, retryCount);
          console.warn(
            "[API] Network error on " +
              fullUrl +
              ", retry " +
              (retryCount + 1) +
              "/" +
              MAX_RETRIES +
              " in " +
              delay +
              "ms",
          );
          setTimeout(function () {
            request(Object.assign({}, opts, { _retryCount: retryCount + 1 }))
              .then(resolve)
              .catch(reject);
          }, delay);
          return;
        }

        reject(new Error("NETWORK_ERROR: " + (err.errMsg || "unknown")));
      },
    });
  });

  if (inFlightKey) {
    IN_FLIGHT_REQUESTS[inFlightKey] = pendingPromise;
    pendingPromise.then(
      function () {
        if (IN_FLIGHT_REQUESTS[inFlightKey] === pendingPromise) {
          delete IN_FLIGHT_REQUESTS[inFlightKey];
        }
      },
      function () {
        if (IN_FLIGHT_REQUESTS[inFlightKey] === pendingPromise) {
          delete IN_FLIGHT_REQUESTS[inFlightKey];
        }
      },
    );
  }

  return pendingPromise;
}

// ── Gateway 接口 ─────────────────────────────────────────────

function regAttribution() {
  try {
    var attr = wx.getStorageSync("reg_attribution") || {};
    return {
      channel: String(attr.ch || ""),
      scene: String(attr.scene || ""),
    };
  } catch (_err) {
    return { channel: "", scene: "" };
  }
}

/** 微信小程序登录 */
function wxLogin(code) {
  return request({
    url: "/api/v1/wechat/mp/login",
    method: "POST",
    data: { code: code },
    useGateway: true,
    noAuth: true,
  });
}

/** 手机号授权快速登录 */
function wxLoginWithPhone(code, phoneCode) {
  var attribution = regAttribution();
  return request({
    url: "/api/v1/wechat/mp/login",
    method: "POST",
    data: {
      code: code,
      phone_code: phoneCode,
      channel: attribution.channel,
      scene: attribution.scene,
    },
    useGateway: true,
    noAuth: true,
  });
}

/** 绑定手机号 */
function bindPhone(phoneCode) {
  var attribution = regAttribution();
  return request({
    url: "/api/v1/wechat/mp/bind-phone",
    method: "POST",
    data: {
      phone_code: phoneCode,
      channel: attribution.channel,
      scene: attribution.scene,
    },
    useGateway: true,
  });
}

// ── 主服务接口 ────────────────────────────────────────────────

/** 获取用户信息 */
function getUserInfo() {
  return requestStateGet("/api/v1/auth/profile");
}

/** 获取今日练习进度 */
function getTodayProgress(opts) {
  return requestStateGet("/api/v1/practice/today-progress", opts);
}

/** 获取章节进度 */
function getChapterProgress() {
  return requestStateGet("/api/v1/practice/chapter-progress");
}

/** 获取用户积分 */
function getPoints() {
  return requestStateGet("/api/v1/billing/points");
}

/** 获取旧版使用概览 */
function getUsage() {
  return requestStateGet("/api/v1/billing/usage");
}

/** 更新用户设置 */
function updateSettings(settings) {
  return request({
    url: "/api/v1/auth/profile/settings",
    method: "PATCH",
    data: settings,
  });
}

/** 获取成就徽章 */
function getBadges() {
  return requestStateGet("/api/v1/profile/badges");
}

/** 获取每日一题 */
function getDailyQuestion() {
  return requestStateGet("/api/v1/practice/daily-question");
}

/** 获取能力雷达数据（8D 维度） */
function getRadarData(userId, opts) {
  return requestStateGet("/api/v1/bi/radar/" + userId, opts);
}

/** 获取掌握度看板（章节掌握度 + 易错热点 + 复习预报） */
function getMasteryDashboard(opts) {
  return requestStateGet("/api/v1/plan/mastery-dashboard", opts);
}

/** 获取 Learning Brain 学习事实编译 read model */
function getLearningBrainProjection(eventLimit, opts) {
  var limit = Number(eventLimit || 100);
  if (!Number.isFinite(limit) || limit <= 0) limit = 100;
  return requestStateGet(
    "/api/v1/learning-brain/projection?event_limit=" +
      Math.min(Math.round(limit), 500),
    opts,
  );
}

/** 获取学情页统一 read model */
function getLearningReport(eventLimit, opts) {
  var limit = Number(eventLimit || 100);
  if (!Number.isFinite(limit) || limit <= 0) limit = 100;
  var options = opts && typeof opts === "object" ? opts : {};
  var schemaVersion = Number(
    options.schemaVersion || options.schema_version || 1,
  );
  var query =
    "/api/v1/mobile/learning-report?event_limit=" +
    Math.min(Math.round(limit), 500);
  if (schemaVersion === 2) query += "&schema_version=2";
  return requestStateGet(query, opts);
}

/** 获取单次作答详情 */
function getLearningAttemptDetail(attemptRef, opts) {
  return requestStateGet(
    "/api/v1/mobile/learning-attempts/" +
      encodeURIComponent(String(attemptRef || "")),
    opts,
  );
}

/** 收藏错题到云端错题集 authority */
function saveMistakeBookItem(payload) {
  return request({
    url: "/api/v1/mobile/mistake-book/items",
    method: "POST",
    data: payload || {},
  });
}

/** 保存 source-linked 学习卡片；后端按 metadata.card_type 分流到 NotebookCardService */
function saveNotebookCard(payload) {
  var input = payload && typeof payload === "object" ? payload : {};
  var metadata = Object.assign({}, input.metadata || {}, {
    card_type: input.card_type || input.cardType || "manual_note",
    subject_id: input.subject_id || input.subjectId || "",
    source_bot_id: input.source_bot_id || input.sourceBotId || "",
    source_type: input.source_type || input.sourceType || "manual",
    source_ref: input.source_ref || input.sourceRef || {},
    evidence_event_ids:
      input.evidence_event_ids || input.evidenceEventIds || [],
    ai_enhanced_content:
      input.ai_enhanced_content || input.aiEnhancedContent || {},
  });
  return request({
    url: "/api/v1/notebook/add_record",
    method: "POST",
    data: {
      notebook_ids: input.notebook_ids || input.notebookIds || [],
      record_type: input.record_type || input.recordType || "chat",
      title: input.title || "学习卡片",
      summary: "",
      user_query: input.user_query || input.userQuery || "",
      output: input.output || "",
      metadata: metadata,
      kb_name: input.kb_name || input.kbName || null,
    },
  });
}

function getMistakeBook(params, opts) {
  var query = [];
  var input = params && typeof params === "object" ? params : {};
  if (input.subject_id || input.subjectId) {
    query.push(
      "subject_id=" +
        encodeURIComponent(String(input.subject_id || input.subjectId)),
    );
  }
  if (
    input.include_mastered !== undefined ||
    input.includeMastered !== undefined
  ) {
    query.push(
      "include_mastered=" +
        encodeURIComponent(
          String(Boolean(input.include_mastered || input.includeMastered)),
        ),
    );
  }
  return requestStateGet(
    "/api/v1/mobile/mistake-book" + (query.length ? "?" + query.join("&") : ""),
    opts,
  );
}

function removeMistakeBookItem(attemptRef) {
  return request({
    url:
      "/api/v1/mobile/mistake-book/items/" +
      encodeURIComponent(String(attemptRef || "")),
    method: "DELETE",
  });
}

function markMistakeBookItemMastered(attemptRef) {
  return request({
    url:
      "/api/v1/mobile/mistake-book/items/" +
      encodeURIComponent(String(attemptRef || "")) +
      "/mastered",
    method: "POST",
    data: {},
  });
}

function recordMistakeBookItemReview(attemptRef) {
  return request({
    url:
      "/api/v1/mobile/mistake-book/items/" +
      encodeURIComponent(String(attemptRef || "")) +
      "/review",
    method: "POST",
    data: {},
  });
}

/** 获取对话列表 */
function getConversations(archived) {
  var url = "/api/v1/conversations";
  if (archived === true) url += "?archived=true";
  return requestStateGet(url);
}

/** 创建新对话 */
function createConversation() {
  return request({ url: "/api/v1/conversations", method: "POST", data: {} });
}

/** 启动一个聊天 turn，返回 conversation / turn / ws 订阅信息 */
function startChatTurn(payload) {
  return request({
    url: "/api/v1/chat/start-turn",
    method: "POST",
    data: payload || {},
  });
}

/** 获取公开运行时能力 */
function getRuntimeCapabilities() {
  return requestStateGet("/api/v1/system/public-capabilities", {
    noAuth: true,
  });
}

/** 获取对话消息 */
function getConversationMessages(convId) {
  return requestStateGet("/api/v1/conversations/" + convId + "/messages");
}

/** 删除对话 */
function deleteConversation(convId) {
  return request({ url: "/api/v1/conversations/" + convId, method: "DELETE" });
}

/** 批量操作对话 (delete / archive / unarchive) */
function batchConversations(action, conversationIds) {
  return request({
    url: "/api/v1/conversations/batch",
    method: "POST",
    data: { action: action, conversation_ids: conversationIds },
  });
}

/** 获取钱包余额 */
function getWallet() {
  return requestStateGet("/api/v1/billing/wallet");
}

/** 获取积分流水（支持分页） */
function getLedger(limit, offset) {
  var q = "?limit=" + (limit || 20);
  if (offset) q += "&offset=" + offset;
  return requestStateGet("/api/v1/billing/ledger" + q);
}

/** 创建会员开通支付订单 */
function createBillingCheckout(payload) {
  return request({
    url: "/api/v1/billing/checkout",
    method: "POST",
    data: payload || {},
  });
}

/** 提交消息反馈（点赞/点踩） */
function submitFeedback(data) {
  var sessionId = String((data && data.conversation_id) || "").trim();
  var messageId = String((data && data.message_id) || "").trim();
  var payload = Object.assign({}, data || {});
  delete payload.conversation_id;
  delete payload.message_id;
  return request({
    url:
      sessionId && messageId
        ? "/api/v1/sessions/" +
          encodeURIComponent(sessionId) +
          "/messages/" +
          encodeURIComponent(messageId) +
          "/feedback"
        : "/api/v1/chat/feedback",
    method: "POST",
    data: payload,
  });
}

/** 上传意见反馈截图/录屏，返回可被 BI 打开的附件 URL */
function uploadFeedbackAttachment(file) {
  var input = file || {};
  var filePath = String(
    input.temp_path || input.tempFilePath || input.path || "",
  ).trim();
  if (!filePath) {
    return Promise.reject(new Error("ATTACHMENT_FILE_REQUIRED"));
  }
  var baseUrl = getBaseUrl(false);
  var token = auth.getToken();
  return new Promise(function (resolve, reject) {
    wx.uploadFile({
      url: baseUrl + "/api/v1/chat/feedback/attachments",
      filePath: filePath,
      name: "file",
      formData: {
        kind: String(input.kind || input.fileType || "image"),
      },
      header: token
        ? {
            Authorization: "Bearer " + token,
            "ngrok-skip-browser-warning": "true",
          }
        : {
            "ngrok-skip-browser-warning": "true",
          },
      timeout: REQUEST_TIMEOUT,
      success: function (res) {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(createHttpError(res.statusCode));
          return;
        }
        var body = res.data;
        if (typeof body === "string") {
          try {
            body = JSON.parse(body);
          } catch (err) {
            reject(new Error("INVALID_UPLOAD_RESPONSE"));
            return;
          }
        }
        resolve((body && body.attachment) || body || {});
      },
      fail: function (err) {
        reject(err || new Error("UPLOAD_FAILED"));
      },
    });
  });
}

/** 获取首页仪表盘（问候/复习/薄弱点） */
function getHomeDashboard(opts) {
  return requestStateGet("/api/v1/homepage/dashboard", opts);
}

/** 首次体验完成 — 服务端按 signed manifest 重新判定并幂等写回 Learner State。 */
function completeFirstRun(payload, opts) {
  return request(
    Object.assign(
      {
        url: "/api/v1/first-run/complete",
        method: "POST",
        data: payload || {},
        noRetry: true,
        noBaseFallback: true,
      },
      opts || {},
    ),
  );
}

// ── 鲁班学习双轮（站点卡 lesson viewmodel，只读投影，零学习证据写入） ──

/** 鲁班 — 绿灯站点列表 */
function getLubanLessons(opts) {
  return requestStateGet("/api/v1/luban/lessons", opts);
}

/** 鲁班 — 单站 viewmodel（card_url / variant_retest 等）。
 * opts.episode 只选择同一 pack 下已发布的教学集；不改变练习/进度的 pack authority。 */
function getLubanLessonDetail(packId, opts) {
  var options = Object.assign({}, opts || {});
  var episode = Number(options.episode || 1);
  if (!Number.isFinite(episode) || episode < 1) episode = 1;
  episode = Math.floor(episode);
  delete options.episode;
  return requestStateGet(
    "/api/v1/luban/lessons/" +
      encodeURIComponent(String(packId || "")) +
      (episode > 1 ? "?episode=" + episode : ""),
    options,
  );
}

/** 鲁班 — 已登录站点向同一张 H5 教学卡签发一次性身份承接凭据。
 * 它不是通用登录 token，只能由该卡用于卡内追问和 lesson_viewed 桥接。 */
function issueLubanCardEntry(packId, episode, opts) {
  var episodeIndex = Number(episode || 1);
  if (!Number.isFinite(episodeIndex) || episodeIndex < 1) episodeIndex = 1;
  return request(
    Object.assign(
      {
        url: "/api/v1/luban/lessons/" + encodeURIComponent(String(packId || "")) + "/card-entry",
        method: "POST",
        data: { episode: Math.floor(episodeIndex) },
        noRetry: true,
      },
      opts || {},
    ),
  );
}

/** 鲁班 — 学-evidence 上报（lesson_viewed，融合计划 §2.1 唯一 writer）。
 * 看完讲懂/闯关幕后调用；后端 progress_countable=false、evidence_level=exposed，
 * 绝不算掌握(M0)。watched_stage: "lesson"(讲懂) | "practice"(闯关)。 */
function postLessonProgress(packId, watchedStage, cardSha, opts) {
  return request(
    Object.assign(
      {
        url: "/api/v1/lesson-progress/progress",
        method: "POST",
        data: {
          pack_id: String(packId || ""),
          watched_stage: String(watchedStage || "lesson"),
          card_sha: String(cardSha || ""),
        },
      },
      opts || {},
    ),
  );
}

/** 鲁班 — 复习到期投影(到期语义权威=revalidation_queue, 双轮 §6)。
 * 旗标(LUBAN_REVIEW_MODULE_ENABLED)关时服务端返空清单(enabled=false), 页面走诚实空态。 */
function getLubanReviewDue(opts) {
  return requestStateGet("/api/v1/luban/review-due", opts);
}

/** 鲁班 — 站完成信号(非 promoting): 复测调度的触发事实——交接时刻/复测完成时上报。
 * 走唯一 learner-signal 写入口, 不写掌握、不进证据编译器(contracts/learner-state.md)。 */
function postStationCompleted(packId, packTitle, completionId, opts) {
  return request(
    Object.assign(
      {
        url: "/api/v1/learner-signal/signal",
        method: "POST",
        data: {
          signal_type: "station_completed",
          concept_id: String(packId || "").trim(),
          concept_label: String(packTitle || "").trim(),
          completion_id: String(completionId || "").trim(),
        },
      },
      opts || {},
    ),
  );
}

/** 鲁班 — 变体题面（服务端确定性抽取并签发 selection identity；客户端只做即时反馈）。
 * mode: "review"（默认，复习轮换皮复测）| "forward"（学习轮 2 分钟正向轻练，
 * 对刚学完 pack 覆盖不同 rule_group 取一组）——同一 builder/端点，仅选序不同。
 * 向后兼容:旧调用把 opts 放第 3 位（getLubanRetestItems(pack, 1, {silent:true})），
 * 第 3 位为对象时按 opts 处理、mode 归 review。 */
function getLubanRetestItems(packId, limit, mode, opts) {
  if (mode && typeof mode === "object") {
    opts = mode;
    mode = "review";
  }
  var n = Number(limit || 5);
  if (!Number.isFinite(n) || n <= 0) n = 5;
  var m = String(mode || "review") === "forward" ? "forward" : "review";
  var practiceSurface = String((opts && opts.practiceSurface) || "").trim();
  var projectionReceipt = String((opts && opts.projectionReceipt) || "").trim();
  var probeId = String((opts && opts.probeId) || "").trim();
  // 错后当场确认(变体判断题消费点1): forward 场传 completion 派生的错题 facts(≤5);
  // 服务端据此走 immediate_confirm 变体供给。空/非 forward = 不传(现行为)。
  var confirmFactsList = (opts && opts.confirmFacts) || [];
  var confirmFacts = (Array.isArray(confirmFactsList) ? confirmFactsList : [])
    .map(function (fact) { return String(fact || "").trim(); })
    .filter(function (fact) { return fact; })
    .slice(0, 5)
    .join(",");
  var confirmAnchor = String((opts && opts.confirmAnchor) || "").trim();
  return requestStateGet(
    "/api/v1/luban/lessons/" +
      encodeURIComponent(String(packId || "")) +
      "/retest-items?limit=" +
      Math.min(Math.round(n), 10) +
      "&mode=" +
      m +
      (practiceSurface ? "&practice_surface=" + encodeURIComponent(practiceSurface) : "") +
      (projectionReceipt ? "&projection_receipt=" + encodeURIComponent(projectionReceipt) : "") +
      (probeId ? "&probe_id=" + encodeURIComponent(probeId) : "") +
      (m === "forward" && confirmFacts ? "&confirm_facts=" + encodeURIComponent(confirmFacts) : "") +
      (m === "forward" && confirmFacts && confirmAnchor
        ? "&confirm_anchor=" + encodeURIComponent(confirmAnchor)
        : ""),
    opts,
  );
}

/** 鲁班 — 复测 completion 唯一写入口。客户端只交选择；服务端按签发题池重判，
 * 全题成功后才提交 terminal + station_completed。 */
function completeLubanRetest(packId, payload, opts) {
  return request(
    Object.assign(
      {
        url:
          "/api/v1/luban/lessons/" +
          encodeURIComponent(String(packId || "")) +
          "/retest-complete",
        method: "POST",
        data: payload || {},
      },
      opts || {},
    ),
  );
}

/** 鲁班 — 实务闯关「全量作答」档(档位③): 自由默写文本提交判分内核。
 * 前端零判分、零改分——只投递 { variant_id, answer_text }, 逐采分点 verdict 由后端
 * 内核给(已剥离 keywords/required_terms, 防再认泄漏)。旗标关 / 未签发 / 非绿灯一律
 * 404 同形——前端据此保持「全量作答即将开通」诚实占位, 绝不本地伪造判分。 */
function postLubanFullAnswer(packId, variantId, answerText, opts) {
  return request(
    Object.assign(
      {
        url:
          "/api/v1/luban/lessons/" +
          encodeURIComponent(String(packId || "")) +
          "/full-answer",
        method: "POST",
        data: {
          variant_id: String(variantId || "").trim(),
          answer_text: String(answerText || ""),
        },
      },
      opts || {},
    ),
  );
}

/** 鲁班 — 考点卡库总览(张数真值=signed 卡池投影; 旗标关返 total=0/enabled=false,
 * 复习页据此保持「即将开通」诚实占位, 前端绝不自造卡数)。 */
function getLubanConceptCardLibrary(opts) {
  return requestStateGet("/api/v1/luban/concept-cards", opts);
}

/** 鲁班 — 单站考点卡(翻卡页数据; 未签发/非绿灯/旗标关一律 404 同形)。 */
function getLubanConceptCards(packId, opts) {
  return requestStateGet(
    "/api/v1/luban/concept-cards/" + encodeURIComponent(String(packId || "")),
    opts,
  );
}

/** 鲁班 — F16 看穿 5天留存内容(表皮试探4选1 + 透视揭底4段 + 暖纠正 + 定位证据带延伸标注)。
 * 全部编译期签发,前端只投影、一字不新造;旗标关 / 未签发 / 非绿灯一律 404 同形。 */
function getLubanSeethrough(packId, opts) {
  return requestStateGet(
    "/api/v1/luban/seethrough/" + encodeURIComponent(String(packId || "")),
    opts,
  );
}

/** 鲁班 — 看穿库总览(天数真值; 旗标关返 total=0/enabled=false)。 */
function getLubanSeethroughLibrary(opts) {
  return requestStateGet("/api/v1/luban/seethrough", opts);
}

/** 鲁班 — 单站 R6 精确挖空(实务闯关②半写数据: recall_prompt + skeleton_sentences
 * [{text_before, blank_hint, text_after}]。签发真值=_{pack}_r6_cloze_bank(signed+sha
 * 双闸); 未签发/非绿灯/旗标关一律 404 同形——闯关据此保持自由默写降级, 不伪装挖空)。 */
function getLubanCloze(packId, opts) {
  return requestStateGet(
    "/api/v1/luban/cloze/" + encodeURIComponent(String(packId || "")),
    opts,
  );
}

/** 鲁班 — 单条 R8 解药(错因银行 detail「解药位」; 按 {pack_id, error_code} 取
 * signed 解药, 响应 {mental_model, textbook_ref}。未签发/无此码/非绿灯/旗标关一律
 * 404 同形——前端据此保持「解药整理中」诚实占位, 绝不自造讲解)。 */
function getLubanAntidote(packId, errorCode, opts) {
  return requestStateGet(
    "/api/v1/luban/antidotes/" +
      encodeURIComponent(String(packId || "")) +
      "/" +
      encodeURIComponent(String(errorCode || "")),
    opts,
  );
}

/** 摸底测试 — 获取诊断档案 */
function getAssessmentProfile(opts) {
  return requestStateGet("/api/v1/assessment/profile", opts);
}

/** 摸底测试 — 获取专题目录 */
function getAssessmentTopics(opts) {
  return requestStateGet("/api/v1/assessment/topics", opts);
}

/** 摸底测试 — 创建测试 */
function createAssessment(type, count) {
  var payload =
    type && typeof type === "object"
      ? Object.assign({}, type)
      : { assessment_type: type || "diagnostic", count: count || 20 };
  return request({
    url: "/api/v1/assessment/create",
    method: "POST",
    data: payload,
    noRetry: true,
    noBaseFallback: true,
  });
}

/** 摸底测试 — 提交答案 */
function submitAssessment(quizId, answers, timeSpent, deviceId) {
  return request({
    url: "/api/v1/assessment/" + quizId + "/submit",
    method: "POST",
    data: { answers: answers, time_spent_seconds: timeSpent, device_id: deviceId || "" },
    noRetry: true,
    noBaseFallback: true,
  });
}

/** 摸底测试 — 恢复答题 */
function getAssessmentSession(quizId, deviceId) {
  var url = "/api/v1/assessment/" + quizId;
  if (deviceId) {
    url += "?device_id=" + encodeURIComponent(deviceId);
  }
  return requestStateGet(url);
}

/** 摸底测试 — 获取报告 */
function getAssessmentReport(quizId) {
  return requestStateGet("/api/v1/assessment/" + quizId + "/report");
}

/** 摸底测试 — 生成 AI 详细解析 */
function requestAssessmentDeepExplanation(quizId, questionId) {
  return request({
    url: "/api/v1/assessment/" + quizId + "/items/" + questionId + "/explain",
    method: "POST",
  });
}

module.exports = {
  request: request,
  ensureFreshAuthToken: ensureFreshAuthToken,
  refreshAuthToken: refreshAuthToken,
  unwrapResponse: unwrapResponse,
  errorCodeOf: errorCodeOf,
  inspectRequestError: inspectRequestError,
  describeRequestError: describeRequestError,
  shouldRetryWechatLogin: shouldRetryWechatLogin,
  wxLogin: wxLogin,
  wxLoginWithPhone: wxLoginWithPhone,
  bindPhone: bindPhone,
  regAttribution: regAttribution,
  getUserInfo: getUserInfo,
  getTodayProgress: getTodayProgress,
  getChapterProgress: getChapterProgress,
  getPoints: getPoints,
  getUsage: getUsage,
  updateSettings: updateSettings,
  getBadges: getBadges,
  getDailyQuestion: getDailyQuestion,
  getRadarData: getRadarData,
  getMasteryDashboard: getMasteryDashboard,
  getLearningReport: getLearningReport,
  getLearningAttemptDetail: getLearningAttemptDetail,
  saveMistakeBookItem: saveMistakeBookItem,
  saveNotebookCard: saveNotebookCard,
  getMistakeBook: getMistakeBook,
  removeMistakeBookItem: removeMistakeBookItem,
  markMistakeBookItemMastered: markMistakeBookItemMastered,
  recordMistakeBookItemReview: recordMistakeBookItemReview,
  getLearningBrainProjection: getLearningBrainProjection,
  getConversations: getConversations,
  createConversation: createConversation,
  startChatTurn: startChatTurn,
  getRuntimeCapabilities: getRuntimeCapabilities,
  getConversationMessages: getConversationMessages,
  deleteConversation: deleteConversation,
  batchConversations: batchConversations,
  getWallet: getWallet,
  getLedger: getLedger,
  createBillingCheckout: createBillingCheckout,
  submitFeedback: submitFeedback,
  uploadFeedbackAttachment: uploadFeedbackAttachment,
  getHomeDashboard: getHomeDashboard,
  completeFirstRun: completeFirstRun,
  getLubanLessons: getLubanLessons,
  getLubanLessonDetail: getLubanLessonDetail,
  issueLubanCardEntry: issueLubanCardEntry,
  getLubanRetestItems: getLubanRetestItems,
  completeLubanRetest: completeLubanRetest,
  getLubanReviewDue: getLubanReviewDue,
  getLubanConceptCardLibrary: getLubanConceptCardLibrary,
  getLubanConceptCards: getLubanConceptCards,
  getLubanSeethrough: getLubanSeethrough,
  getLubanSeethroughLibrary: getLubanSeethroughLibrary,
  getLubanCloze: getLubanCloze,
  getLubanAntidote: getLubanAntidote,
  postLubanFullAnswer: postLubanFullAnswer,
  postStationCompleted: postStationCompleted,
  postLessonProgress: postLessonProgress,
  getAssessmentProfile: getAssessmentProfile,
  getAssessmentTopics: getAssessmentTopics,
  createAssessment: createAssessment,
  getAssessmentSession: getAssessmentSession,
  getAssessmentReport: getAssessmentReport,
  submitAssessment: submitAssessment,
  requestAssessmentDeepExplanation: requestAssessmentDeepExplanation,
};
