// 学情快照仅是可丢弃的 UI 加速层；canonical truth 仍在服务端 learning report。
// 本模块唯一拥有缓存 key/envelope，防页面与 logout 各复制一套字符串协议。
var BASE_KEY = "deeptutor.report.unifiedSnapshot.v2";
var ownerStorage = require("./owner-storage");

function _userId(value) {
  return String(value || "").trim();
}

function keyFor(userId) {
  return ownerStorage.keyFor(BASE_KEY, _userId(userId));
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
    var cached = ownerStorage.read(BASE_KEY, normalized);
    if (!cached || typeof cached !== "object") return null;
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
    return ownerStorage.write(BASE_KEY, normalized, {
      cachedAt: Date.now(), snapshot: snapshot,
    });
  } catch (_) {
    return false;
  }
}

function clear(userId) {
  var key = keyFor(userId);
  if (!key) return false;
  try {
    return ownerStorage.remove(BASE_KEY, userId);
  } catch (_) {
    return false;
  }
}

module.exports = { keyFor: keyFor, read: read, write: write, clear: clear };
