// utils/api.js — Gateway / 主服务 HTTP 请求封装
const auth = require("./auth");
const endpoints = require("./endpoints");
const runtime = require("./runtime");

// ── 常量 ──────────────────────────────────────────────────
var MAX_RETRIES = 2; // 最大重试次数
var RETRY_BASE_DELAY = 1000; // 首次重试延迟 ms
var REQUEST_TIMEOUT = 15000; // 请求超时 ms
var RETRYABLE_METHODS = { GET: true, PUT: true, DELETE: true }; // 幂等方法才重试

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

/**
 * 通用请求（带 token 自动注入 + 指数退避重试 + Token 刷新）
 * @param {object} opts - { url, method, data, useGateway, noAuth, _retryCount }
 */
function request(opts) {
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

  var header = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
  };
  if (!noAuth && token) {
    header["Authorization"] = "Bearer " + token;
  }

  return new Promise(function (resolve, reject) {
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
  return request({ url: "/api/v1/auth/profile", method: "GET" });
}

/** 获取今日练习进度 */
function getTodayProgress() {
  return request({ url: "/api/v1/practice/today-progress", method: "GET" });
}

/** 获取章节进度 */
function getChapterProgress() {
  return request({ url: "/api/v1/practice/chapter-progress", method: "GET" });
}

/** 获取用户积分 */
function getPoints() {
  return request({ url: "/api/v1/billing/points", method: "GET" });
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
  return request({ url: "/api/v1/profile/badges", method: "GET" });
}

/** 获取每日一题 */
function getDailyQuestion() {
  return request({ url: "/api/v1/practice/daily-question", method: "GET" });
}

/** 获取能力雷达数据（8D 维度） */
function getRadarData(userId) {
  return request({
    url: "/api/v1/bi/radar/" + userId,
    method: "GET",
  });
}

/** 获取掌握度看板（章节掌握度 + 易错热点 + 复习预报） */
function getMasteryDashboard() {
  return request({
    url: "/api/v1/plan/mastery-dashboard",
    method: "GET",
  });
}

/** 获取对话列表 */
function getConversations(archived) {
  var url = "/api/v1/conversations";
  if (archived === true) url += "?archived=true";
  return request({ url: url, method: "GET" });
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
  return request({
    url: "/api/v1/conversations/" + convId + "/messages",
    method: "GET",
  });
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
  return request({ url: "/api/v1/billing/wallet", method: "GET" });
}

/** 获取积分流水（支持分页） */
function getLedger(limit, offset) {
  var q = "?limit=" + (limit || 20);
  if (offset) q += "&offset=" + offset;
  return request({
    url: "/api/v1/billing/ledger" + q,
    method: "GET",
  });
}

/** 提交消息反馈（点赞/点踩） */
function submitFeedback(data) {
  return request({
    url: "/api/v1/chat/feedback",
    method: "POST",
    data: data,
  });
}

/** 获取首页仪表盘（问候/复习/薄弱点） */
function getHomeDashboard() {
  return request({ url: "/api/v1/homepage/dashboard", method: "GET" });
}

/** 摸底测试 — 获取诊断档案 */
function getAssessmentProfile() {
  return request({ url: "/api/v1/assessment/profile", method: "GET" });
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
  unwrapResponse: unwrapResponse,
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
