// 学情快照仅是可丢弃的 UI 加速层；canonical truth 仍在服务端 learning report。
// 本模块唯一拥有缓存 key/envelope，防页面与 logout 各复制一套字符串协议。
var BASE_KEY = "deeptutor.report.unifiedSnapshot.v2";

function _userId(value) {
  return String(value || "").trim();
}

function keyFor(userId) {
  var normalized = _userId(userId);
  return normalized ? BASE_KEY + ":" + encodeURIComponent(normalized) : "";
}

function _snapshotUserId(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return "";
  var report = snapshot.report && typeof snapshot.report === "object" ? snapshot.report : {};
  return _userId(report.user_id || snapshot.user_id);
}

function read(userId, maxAgeMs) {
  var normalized = _userId(userId);
  var key = keyFor(normalized);
  if (!key || typeof wx === "undefined" || typeof wx.getStorageSync !== "function") return null;
  try {
    var cached = wx.getStorageSync(key);
    if (!cached || typeof cached !== "object" || cached.userId !== normalized) return null;
    if (!cached.snapshot || typeof cached.snapshot !== "object") return null;
    var snapshotUserId = _snapshotUserId(cached.snapshot);
    if (snapshotUserId && snapshotUserId !== normalized) return null;
    var cachedAt = Number(cached.cachedAt) || 0;
    if (!cachedAt || Date.now() - cachedAt > Number(maxAgeMs || 0)) return null;
    return cached.snapshot;
  } catch (_) {
    return null;
  }
}

function write(userId, snapshot) {
  var normalized = _userId(userId);
  var key = keyFor(normalized);
  if (!key || !snapshot || typeof snapshot !== "object") return false;
  var snapshotUserId = _snapshotUserId(snapshot);
  if (snapshotUserId && snapshotUserId !== normalized) return false;
  try {
    if (typeof wx === "undefined" || typeof wx.setStorageSync !== "function") return false;
    wx.setStorageSync(key, { userId: normalized, cachedAt: Date.now(), snapshot: snapshot });
    return true;
  } catch (_) {
    return false;
  }
}

function clear(userId) {
  var key = keyFor(userId);
  if (!key) return false;
  try {
    if (typeof wx === "undefined" || typeof wx.removeStorageSync !== "function") return false;
    wx.removeStorageSync(key);
    return true;
  } catch (_) {
    return false;
  }
}

module.exports = { keyFor: keyFor, read: read, write: write, clear: clear };
