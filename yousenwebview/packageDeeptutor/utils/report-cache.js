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

// 「新鲜即跳过网络」的唯一阈值:页面进入时快照年龄低于此值,静默刷新也省掉。
// 子页返回(刚发生学习动作)的强制刷新不受此值约束,由页面显式 force。
var FRESH_MAX_AGE_MS = 60 * 1000;

// 快照可用上限:超过此年龄视为不存在(与 report 页原 REPORT_SNAPSHOT_CACHE_MAX_AGE_MS
// 同值收权至此,三个消费页共用,防止各页复制阈值)。
var SNAPSHOT_MAX_AGE_MS = 30 * 60 * 1000;

function readWithMeta(userId, maxAgeMs) {
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
    if (!cachedAt) return null;
    var ageMs = Date.now() - cachedAt;
    if (ageMs > Number(maxAgeMs || 0)) return null;
    return { snapshot: cached.snapshot, ageMs: ageMs };
  } catch (_) {
    return null;
  }
}

function read(userId, maxAgeMs) {
  var hit = readWithMeta(userId, maxAgeMs);
  return hit ? hit.snapshot : null;
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

module.exports = {
  keyFor: keyFor,
  read: read,
  readWithMeta: readWithMeta,
  write: write,
  clear: clear,
  FRESH_MAX_AGE_MS: FRESH_MAX_AGE_MS,
  SNAPSHOT_MAX_AGE_MS: SNAPSHOT_MAX_AGE_MS,
};
