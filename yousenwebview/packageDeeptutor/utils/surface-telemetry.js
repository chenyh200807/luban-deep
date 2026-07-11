const auth = require("./auth");
const endpoints = require("./endpoints");

var sentEventKeys = {};
var PENDING_EVENTS_MAX = 20;
var pendingEvents = [];

function buildEventId() {
  return (
    "yousen_" +
    Date.now().toString(36) +
    "_" +
    Math.random().toString(36).slice(2, 10)
  );
}

function enqueuePendingEvent(event) {
  if (pendingEvents.length >= PENDING_EVENTS_MAX) {
    pendingEvents.shift();
  }
  pendingEvents.push(event);
}

function buildEvent(eventName, data, collectedAtMs) {
  return {
    eventId: buildEventId(),
    eventName: eventName,
    data: data,
    collectedAtMs: collectedAtMs,
  };
}

function deliverEvent(event, token) {
  var baseUrl = endpoints.getPrimaryBaseUrl(false);
  if (!baseUrl) {
    enqueuePendingEvent(event);
    return;
  }
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
        event_id: event.eventId,
        surface: "wechat_yousenwebview",
        event_name: String(event.eventName || "").trim(),
        session_id: event.data.sessionId || "",
        turn_id: event.data.turnId || "",
        collected_at_ms: event.collectedAtMs,
        sent_at_ms: Date.now(),
        metadata: event.data.metadata || {},
      },
      fail: function () {
        enqueuePendingEvent(event);
      },
    });
  } catch (_) {
    enqueuePendingEvent(event);
  }
}

function flushPendingEvents(token) {
  if (!pendingEvents.length) return;
  var queued = pendingEvents;
  pendingEvents = [];
  for (var i = 0; i < queued.length; i++) {
    deliverEvent(queued[i], token);
  }
}

function track(eventName, payload) {
  if (!eventName || typeof wx === "undefined" || typeof wx.request !== "function") {
    return;
  }
  var data = payload && typeof payload === "object" ? payload : {};
  var event = buildEvent(eventName, data, Date.now());
  var token = auth.getToken();
  if (!token) {
    enqueuePendingEvent(event);
    return;
  }
  flushPendingEvents(token);
  deliverEvent(event, token);
}

function trackOnce(uniqueKey, eventName, payload) {
  var key = String(uniqueKey || "").trim();
  if (!key) {
    track(eventName, payload);
    return;
  }
  if (sentEventKeys[key]) return;
  sentEventKeys[key] = true;
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
    var id = "yousen_visit_" + buildEventId();
    wx.setStorageSync(key, { id: id, touchedAt: now });
    return id;
  } catch (_) {
    return "yousen_visit_" + buildEventId();
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
      // spike 命门判别位：forward(学习轮当天轻练)/review(复习轮次日复测)。
      // 必须在此跳显式导出,否则固定 metadata 会静默丢掉——D1 留存即读不出。
      practice_mode: data.practiceMode || "",
    },
  });
}

module.exports = {
  getOrCreateVisitId: getOrCreateVisitId,
  track: track,
  trackOnce: trackOnce,
  trackProductBehavior: trackProductBehavior,
};
