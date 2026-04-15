function sanitizeValue(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "boolean") return value ? "1" : "0";
  if (typeof value === "number") return isFinite(value) ? String(value) : "";
  return String(value).slice(0, 120);
}

function sanitizePayload(payload) {
  var source = payload && typeof payload === "object" ? payload : {};
  var next = {};
  Object.keys(source).forEach(function (key) {
    next[key] = sanitizeValue(source[key]);
  });
  return next;
}

function track(eventName, payload) {
  var name = String(eventName || "").trim();
  if (!name) return;
  var data = sanitizePayload(payload);
  try {
    if (typeof wx.reportAnalytics === "function") {
      wx.reportAnalytics(name, data);
    }
  } catch (_) {}
}

module.exports = {
  track: track,
};
