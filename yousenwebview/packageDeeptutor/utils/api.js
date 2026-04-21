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
function unwrapResponse(raw) {
  if (!raw || typeof raw !== "object") return raw;
  // 如果有 data 字段且不是基础类型列表（排除 {data: "string"} 的情况）
  if (raw.data !== undefined && typeof raw.data === "object") return raw.data;
  return raw;
}

function parseHttpError(message) {
  var match = /^HTTP_(\d+):\s*(.*)$/.exec(String(message || ""));
  if (!match) {
    return { status: 0, payload: null, detailText: "" };
  }
  var payloadText = String(match[2] || "").trim();
  var payload = null;
  var detailText = payloadText;
  if (payloadText) {
    try {
      payload = JSON.parse(payloadText);
      if (payload && typeof payload === "object" && payload.detail !== undefined) {
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
      return "微信登录服务响应超时，请稍后重试";
    }
    return "请求超时，请稍后重试";
  }
  if (info.isNetworkError) {
    return "连接服务器失败，请检查网络后重试";
  }
  if (info.status >= 500) {
    if (options.context === "wechat_login") {
      if (info.detailText.toLowerCase().indexOf("getuserphonenumber") >= 0) {
        return "微信手机号授权服务暂时不可用，请稍后重试";
      }
      return "微信登录服务暂时不稳定，请稍后重试";
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
  auth.setToken(body.token, body.expires_at);
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
  var baseCandidates = opts._baseCandidates ||
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

        if (
          !opts.url.startsWith("http") &&
          res.statusCode === 404 &&
          baseIndex + 1 < baseCandidates.length
        ) {
          var nextBaseOn404 = baseCandidates[baseIndex + 1];
          console.warn(
            "[API] HTTP 404 on " + fullUrl + ", fallback to " + nextBaseOn404,
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

        if (res.statusCode === 401) {
          if (noAuth) {
            reject(
              new Error("HTTP_401: " + JSON.stringify(res.data)),
            );
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

        if (res.statusCode === 503) {
          var e503 = new Error("FEATURE_DISABLED");
          e503.code = "FEATURE_DISABLED";
          reject(e503);
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

        reject(
          new Error("HTTP_" + res.statusCode + ": " + JSON.stringify(res.data)),
        );
      },
      fail: function (err) {
        if (err.errMsg && err.errMsg.includes("abort")) {
          reject(new Error("REQUEST_ABORTED"));
          return;
        }

        if (
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
    pendingPromise.then(function () {
      if (IN_FLIGHT_REQUESTS[inFlightKey] === pendingPromise) {
        delete IN_FLIGHT_REQUESTS[inFlightKey];
      }
    }, function () {
      if (IN_FLIGHT_REQUESTS[inFlightKey] === pendingPromise) {
        delete IN_FLIGHT_REQUESTS[inFlightKey];
      }
    });
  }

  return pendingPromise;
}

// ── Gateway 接口 ─────────────────────────────────────────────

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

/** 绑定手机号 */
function bindPhone(phoneCode) {
  return request({
    url: "/api/v1/wechat/mp/bind-phone",
    method: "POST",
    data: { phone_code: phoneCode },
    useGateway: true,
  });
}

// ── 主服务接口 ────────────────────────────────────────────────

/** 获取用户信息 */
function getUserInfo() {
  return requestStateGet("/api/v1/auth/profile");
}

/** 获取今日练习进度 */
function getTodayProgress() {
  return requestStateGet("/api/v1/practice/today-progress");
}

/** 获取章节进度 */
function getChapterProgress() {
  return requestStateGet("/api/v1/practice/chapter-progress");
}

/** 获取用户积分 */
function getPoints() {
  return requestStateGet("/api/v1/billing/points");
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
function getRadarData(userId) {
  return requestStateGet("/api/v1/bi/radar/" + userId);
}

/** 获取掌握度看板（章节掌握度 + 易错热点 + 复习预报） */
function getMasteryDashboard() {
  return requestStateGet("/api/v1/plan/mastery-dashboard");
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

/** 获取首页仪表盘（问候/复习/薄弱点） */
function getHomeDashboard() {
  return requestStateGet("/api/v1/homepage/dashboard");
}

/** 摸底测试 — 获取诊断档案 */
function getAssessmentProfile() {
  return requestStateGet("/api/v1/assessment/profile");
}

/** 摸底测试 — 创建测试 */
function createAssessment(type, count) {
  return request({
    url: "/api/v1/assessment/create",
    method: "POST",
    data: { assessment_type: type || "diagnostic", count: count || 20 },
  });
}

/** 摸底测试 — 提交答案 */
function submitAssessment(quizId, answers, timeSpent) {
  return request({
    url: "/api/v1/assessment/" + quizId + "/submit",
    method: "POST",
    data: { answers: answers, time_spent_seconds: timeSpent },
  });
}

module.exports = {
  request: request,
  ensureFreshAuthToken: ensureFreshAuthToken,
  refreshAuthToken: refreshAuthToken,
  unwrapResponse: unwrapResponse,
  inspectRequestError: inspectRequestError,
  describeRequestError: describeRequestError,
  shouldRetryWechatLogin: shouldRetryWechatLogin,
  wxLogin: wxLogin,
  bindPhone: bindPhone,
  getUserInfo: getUserInfo,
  getTodayProgress: getTodayProgress,
  getChapterProgress: getChapterProgress,
  getPoints: getPoints,
  updateSettings: updateSettings,
  getBadges: getBadges,
  getDailyQuestion: getDailyQuestion,
  getRadarData: getRadarData,
  getMasteryDashboard: getMasteryDashboard,
  getConversations: getConversations,
  createConversation: createConversation,
  startChatTurn: startChatTurn,
  getConversationMessages: getConversationMessages,
  deleteConversation: deleteConversation,
  batchConversations: batchConversations,
  getWallet: getWallet,
  getLedger: getLedger,
  submitFeedback: submitFeedback,
  getHomeDashboard: getHomeDashboard,
  getAssessmentProfile: getAssessmentProfile,
  createAssessment: createAssessment,
  submitAssessment: submitAssessment,
};
