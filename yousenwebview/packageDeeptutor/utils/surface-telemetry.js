const auth = require("./auth");
const endpoints = require("./endpoints");

var sentEventKeys = {};
var PENDING_EVENTS_MAX = 20;
var PENDING_EVENTS_STORAGE_KEY = "deeptutor_surface_telemetry_pending_v1";
var pendingEvents = null;
var inFlightEventIds = {};

function currentOwnerId() {
  try {
    return String((auth && auth.getUserId && auth.getUserId()) || "").trim();
  } catch (_) {
    return "";
  }
}

function readPendingEvents() {
  if (pendingEvents) return pendingEvents;
  try {
    var stored = wx.getStorageSync(PENDING_EVENTS_STORAGE_KEY);
    pendingEvents = Array.isArray(stored) ? stored.slice(-PENDING_EVENTS_MAX) : [];
  } catch (_) {
    pendingEvents = [];
  }
  return pendingEvents;
}

function persistPendingEvents() {
  try {
    wx.setStorageSync(PENDING_EVENTS_STORAGE_KEY, readPendingEvents());
  } catch (_) {}
}

function buildEventId() {
  return (
    "yousen_" +
    Date.now().toString(36) +
    "_" +
    Math.random().toString(36).slice(2, 10)
  );
}

function enqueuePendingEvent(event) {
  var queue = readPendingEvents();
  if (queue.some(function (item) { return item.eventId === event.eventId; })) return;
  if (queue.length >= PENDING_EVENTS_MAX) {
    queue.shift();
  }
  queue.push(event);
  persistPendingEvents();
}

function acknowledgePendingEvent(eventId) {
  pendingEvents = readPendingEvents().filter(function (event) {
    return event.eventId !== eventId;
  });
  persistPendingEvents();
}

function buildEvent(eventName, data, collectedAtMs) {
  return {
    eventId: buildEventId(),
    eventName: eventName,
    data: data,
    ownerId: currentOwnerId(),
    collectedAtMs: collectedAtMs,
  };
}

function deliverEvent(event, token) {
  enqueuePendingEvent(event);
  var baseUrl = endpoints.getPrimaryBaseUrl(false);
  if (!baseUrl) {
    enqueuePendingEvent(event);
    return;
  }
  if (inFlightEventIds[event.eventId]) return;
  inFlightEventIds[event.eventId] = true;
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
        event_version: event.data.eventVersion || 1,
        surface: "wechat_yousenwebview",
        event_name: String(event.eventName || "").trim(),
        session_id: event.data.sessionId || "",
        turn_id: event.data.turnId || "",
        collected_at_ms: event.collectedAtMs,
        sent_at_ms: Date.now(),
        metadata: event.data.metadata || {},
      },
      success: function (response) {
        delete inFlightEventIds[event.eventId];
        var body = (response && response.data) || {};
        var durableFailure = body.product_behavior_status === "persistence_failed";
        if (!durableFailure && (body.accepted === true || body.status === "duplicate")) {
          acknowledgePendingEvent(event.eventId);
        }
      },
      fail: function () {
        delete inFlightEventIds[event.eventId];
        persistPendingEvents();
      },
    });
  } catch (_) {
    delete inFlightEventIds[event.eventId];
    enqueuePendingEvent(event);
  }
}

function flushPendingEvents(token) {
  var ownerId = currentOwnerId();
  var retained = readPendingEvents().filter(function (event) {
    return !!event.ownerId && !!ownerId && event.ownerId === ownerId;
  });
  if (retained.length !== readPendingEvents().length) {
    pendingEvents = retained;
    persistPendingEvents();
  }
  var queued = retained.slice();
  if (!queued.length) return;
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
    eventVersion: data.eventVersion || 1,
    sessionId: data.sessionId || "",
    turnId: data.turnId || "",
    metadata: {
      event_version: data.eventVersion || 1,
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

function trackModuleView(page, payload) {
  if (!page || page.__productBehaviorVisit) return;
  var data = payload && typeof payload === "object" ? payload : {};
  var visitId = getOrCreateVisitId();
  page.__productBehaviorVisit = {
    visitId: visitId,
    startedAt: Date.now(),
    module: data.module || "",
    section: data.section || "home",
  };
  trackProductBehavior("module_viewed", {
    visitId: visitId,
    module: data.module || "",
    section: data.section || "home",
    action: "view",
  });
}

function trackModuleExit(page, overrides) {
  if (!page || !page.__productBehaviorVisit) return;
  var active = page.__productBehaviorVisit;
  page.__productBehaviorVisit = null;
  var extra = overrides && typeof overrides === "object" ? overrides : {};
  trackProductBehavior("module_exited", {
    visitId: active.visitId,
    module: active.module,
    section: active.section,
    action: extra.action || "return",
    objectType: extra.objectType || "",
    objectId: extra.objectId || "",
    result: extra.result || "",
    durationMs: Math.max(0, Date.now() - active.startedAt),
  });
}

module.exports = {
  getOrCreateVisitId: getOrCreateVisitId,
  track: track,
  trackOnce: trackOnce,
  trackProductBehavior: trackProductBehavior,
  trackModuleView: trackModuleView,
  trackModuleExit: trackModuleExit,
};
