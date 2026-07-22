const auth = require("./auth");
const endpoints = require("./endpoints");

var sentEventKeys = {};
var PENDING_EVENTS_MAX = 20;
var PENDING_EVENTS_STORAGE_KEY = "deeptutor_surface_telemetry_pending_v1";
var pendingEvents = null;
var inFlightEventIds = {};
var runtimeMetadata = null;

// 投递背压（2026-07-19）：旧实现每次 track 全量重放 pending 队列且失败无退避，
// 网络故障时单次 track 放大成最多 21 个请求，吃满 wx.request 10 并发槽位，
// 饿死 lessons/dashboard 等业务请求（练习返回页白屏事故）。
// 连续失败 >=2 次后指数退避；退避窗口内 track 只入队不发网。
var BACKOFF_ACTIVATE_AFTER_FAILURES = 2;
var BACKOFF_BASE_MS = 2000;
var BACKOFF_MAX_MS = 60000;
// 并发收口(2026-07-21,补齐 07-19 只修一半的缺口):退避只挡了"连续失败后",
// 首轮 flush 仍可 21 并发打满 wx.request 10 槽饿死业务请求;且无 timeout 时
// 默认 60s,弱网下每条失败前占槽 1 分钟。telemetry 是旁路观测,永远只许占
// 少量槽位、快速失败;事件已先入队,超限/超时都不丢事件。
var MAX_IN_FLIGHT_DELIVERIES = 2;
var DELIVERY_TIMEOUT_MS = 10000;
var consecutiveDeliveryFailures = 0;
var deliveryBackoffUntilMs = 0;

function registerDeliveryFailure() {
  consecutiveDeliveryFailures += 1;
  if (consecutiveDeliveryFailures >= BACKOFF_ACTIVATE_AFTER_FAILURES) {
    var exponent = Math.min(
      consecutiveDeliveryFailures - BACKOFF_ACTIVATE_AFTER_FAILURES,
      5,
    );
    var delayMs = Math.min(BACKOFF_BASE_MS * Math.pow(2, exponent), BACKOFF_MAX_MS);
    deliveryBackoffUntilMs = Date.now() + delayMs;
  }
}

function registerDeliverySuccess() {
  consecutiveDeliveryFailures = 0;
  deliveryBackoffUntilMs = 0;
}

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
  if (Object.keys(inFlightEventIds).length >= MAX_IN_FLIGHT_DELIVERIES) {
    // 事件已在 pending 队列(deliverEvent 入口先 enqueue),下轮 flush 自然补发。
    return;
  }
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
      timeout: DELIVERY_TIMEOUT_MS,
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
        var statusCode = (response && response.statusCode) || 0;
        if (statusCode >= 400) {
          var retryable =
            statusCode === 401 ||
            statusCode === 408 ||
            statusCode === 429 ||
            statusCode >= 500;
          if (retryable) {
            // 401=token 过期等新 token；429/5xx=服务端暂时不可用。保留在队列并退避。
            registerDeliveryFailure();
            return;
          }
          // 服务端明确终结拒收（400/403/422 等）：重发同一载荷无意义，
          // 必须出队——否则事件永不出队，队列涨满后放大后续所有 track。
          registerDeliverySuccess();
          acknowledgePendingEvent(event.eventId);
          return;
        }
        var body = (response && response.data) || {};
        var durableFailure = body.product_behavior_status === "persistence_failed";
        if (!durableFailure && (body.accepted === true || body.status === "duplicate")) {
          registerDeliverySuccess();
          acknowledgePendingEvent(event.eventId);
          return;
        }
        registerDeliveryFailure();
      },
      fail: function () {
        delete inFlightEventIds[event.eventId];
        registerDeliveryFailure();
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
  if (Date.now() < deliveryBackoffUntilMs) {
    // 退避窗口内只入队不发网，把并发槽位让给业务请求。
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

function getRuntimeMetadata() {
  if (runtimeMetadata) return runtimeMetadata;
  var appVersion = "";
  var platform = "";
  var envVersion = "";
  var wechatVersion = "";
  try {
    if (typeof wx.getAccountInfoSync === "function") {
      var accountInfo = wx.getAccountInfoSync() || {};
      var miniProgram = accountInfo.miniProgram || {};
      appVersion = String(miniProgram.version || "").trim();
      envVersion = String(miniProgram.envVersion || "").trim();
    }
  } catch (_) {}
  try {
    if (typeof wx.getSystemInfoSync === "function") {
      var systemInfo = wx.getSystemInfoSync() || {};
      platform = String(systemInfo.platform || "").trim();
      wechatVersion = String(systemInfo.version || "").trim();
    }
  } catch (_) {}
  if (!appVersion) {
    appVersion = [envVersion, wechatVersion].filter(Boolean).join(":");
  }
  runtimeMetadata = { appVersion: appVersion, platform: platform };
  return runtimeMetadata;
}

function trackProductBehavior(eventName, payload) {
  var data = payload && typeof payload === "object" ? payload : {};
  var visitId = data.visitId || getOrCreateVisitId();
  var runtime = getRuntimeMetadata();
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
      app_version: data.appVersion || runtime.appVersion,
      platform: data.platform || runtime.platform,
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
