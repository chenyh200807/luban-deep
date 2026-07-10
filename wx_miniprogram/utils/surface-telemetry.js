const auth = require("./auth");
const endpoints = require("./endpoints");

var sentEventKeys = {};

// /surface-events 强制登录（SR1 PR-1b）：无 token 的请求会被 401 拒收。
// 登录页曝光/授权点击等 pre-auth 事件先入队，登录成功后随下一条带
// token 的事件冲刷（collected_at_ms 保留真实采集时刻）。
var PENDING_EVENTS_MAX = 20;
var pendingEvents = [];

function buildEventId() {
  return (
    "wx_" +
    Date.now().toString(36) +
    "_" +
    Math.random().toString(36).slice(2, 10)
  );
}

function deliverEvent(eventName, data, collectedAtMs, token) {
  var baseUrl = endpoints.getPrimaryBaseUrl(false);
  if (!baseUrl) return;
  var headers = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
    Authorization: "Bearer " + token,
  };
  try {
    wx.request({
      url: baseUrl + "/api/v1/observability/surface-events",
      method: "POST",
      header: headers,
      data: {
        event_id: buildEventId(),
        surface: "wechat_miniprogram",
        event_name: String(eventName || "").trim(),
        session_id: data.sessionId || "",
        turn_id: data.turnId || "",
        collected_at_ms: collectedAtMs,
        sent_at_ms: Date.now(),
        metadata: data.metadata || {},
      },
      fail: function () {},
    });
  } catch (_) {}
}

function flushPendingEvents(token) {
  if (!pendingEvents.length) return;
  var queued = pendingEvents;
  pendingEvents = [];
  for (var i = 0; i < queued.length; i++) {
    deliverEvent(
      queued[i].eventName,
      queued[i].data,
      queued[i].collectedAtMs,
      token,
    );
  }
}

function track(eventName, payload) {
  if (
    !eventName ||
    typeof wx === "undefined" ||
    typeof wx.request !== "function"
  ) {
    return;
  }
  var collectedAtMs = Date.now();
  var data = payload && typeof payload === "object" ? payload : {};
  var token = auth.getToken();
  if (!token) {
    if (pendingEvents.length >= PENDING_EVENTS_MAX) {
      pendingEvents.shift();
    }
    pendingEvents.push({
      eventName: eventName,
      data: data,
      collectedAtMs: collectedAtMs,
    });
    return;
  }
  flushPendingEvents(token);
  deliverEvent(eventName, data, collectedAtMs, token);
}

function trackOnce(uniqueKey, eventName, payload) {
  var key = String(uniqueKey || "").trim();
  if (!key) {
    track(eventName, payload);
    return;
  }
  var visitId = getOrCreateVisitId();
  var scopedKey = visitId + "::" + key;
  if (sentEventKeys[scopedKey]) return;
  sentEventKeys[scopedKey] = true;
  track(eventName, payload);
}

function getOrCreateVisitId() {
  var key = "deeptutor_behavior_visit_id";
  var now = Date.now();
  var maxAgeMs = 30 * 60 * 1000;
  try {
    var raw = wx.getStorageSync(key);
    if (raw && raw.id && raw.touchedAt && now - raw.touchedAt < maxAgeMs) {
      wx.setStorageSync(key, { id: raw.id, touchedAt: now });
      return raw.id;
    }
    var id = "wx_visit_" + buildEventId();
    wx.setStorageSync(key, { id: id, touchedAt: now });
    return id;
  } catch (_) {
    return "wx_visit_" + buildEventId();
  }
}

function trackProductBehavior(eventName, payload) {
  var data = payload && typeof payload === "object" ? payload : {};
  var visitId = data.visitId || getOrCreateVisitId();
  track(eventName, {
    sessionId: data.sessionId || "",
    turnId: data.turnId || "",
    metadata: {
      visit_id: visitId,
      module: data.module || "",
      section: data.section || "",
      action: data.action || "",
      object_type: data.objectType || "",
      object_id: data.objectId || "",
      entry_source: data.entrySource || "",
      referrer_module: data.referrerModule || "",
      duration_ms: data.durationMs || 0,
      visible_ms: data.visibleMs || 0,
      result: data.result || "",
      error_code: data.errorCode || "",
      release_id: data.releaseId || "",
      app_version: data.appVersion || "",
      platform: data.platform || "",
      device_model: data.deviceModel || "",
      network_type: data.networkType || "",
    },
  });
}

function resetForTests() {
  sentEventKeys = {};
  pendingEvents = [];
}

module.exports = {
  getOrCreateVisitId: getOrCreateVisitId,
  track: track,
  trackOnce: trackOnce,
  trackProductBehavior: trackProductBehavior,
  resetForTests: resetForTests,
};
