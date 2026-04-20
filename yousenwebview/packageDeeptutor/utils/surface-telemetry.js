const auth = require("./auth");
const endpoints = require("./endpoints");

var sentEventKeys = {};

function buildEventId() {
  return (
    "yousen_" +
    Date.now().toString(36) +
    "_" +
    Math.random().toString(36).slice(2, 10)
  );
}

function track(eventName, payload) {
  if (!eventName || typeof wx === "undefined" || typeof wx.request !== "function") {
    return;
  }
  var baseUrl = endpoints.getPrimaryBaseUrl(false);
  if (!baseUrl) return;
  var token = auth.getToken();
  var collectedAtMs = Date.now();
  var data = payload && typeof payload === "object" ? payload : {};
  var headers = {
    "Content-Type": "application/json",
    "ngrok-skip-browser-warning": "true",
  };
  if (token) {
    headers.Authorization = "Bearer " + token;
  }
  try {
    wx.request({
      url: baseUrl + "/api/v1/observability/surface-events",
      method: "POST",
      header: headers,
      data: {
        event_id: buildEventId(),
        surface: "wechat_yousenwebview",
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

module.exports = {
  track: track,
  trackOnce: trackOnce,
};
