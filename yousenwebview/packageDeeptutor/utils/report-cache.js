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

// 快照可用上限:超过此年龄视为不存在(与 report 页原 REPORT_SNAPSHOT_CACHE_MAX_AGE_MS
// 同值收权至此,三个消费页共用,防止各页复制阈值)。
// 注:曾有 FRESH_MAX_AGE_MS「新鲜即跳过网络」门,被对抗 review 证伪后删除——
// 它会把陈旧/降级/半残快照钉成终态。现行统一策略=缓存秒渲染+始终静默刷新。
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
    // 负年龄=设备时钟回拨后的"来自未来"快照,视为无效(否则永不过期)。
    if (ageMs < 0 || ageMs > Number(maxAgeMs || 0)) return null;
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

// 双写者(report/learn 页)写序守卫:以「发起拉取的时刻」竞争。孤儿响应
// (页面已销毁的在途请求,发起时刻早于现存快照的写入时刻)禁写,防止
// 3-5s 慢请求把"动作前旧数据"盖在别页刚写入的新快照上(ABA)。
function writeIfFresher(userId, snapshot, fetchStartedAt) {
  var startedAt = Number(fetchStartedAt) || 0;
  if (startedAt > 0) {
    var existing = readWithMeta(userId, SNAPSHOT_MAX_AGE_MS);
    if (existing && Date.now() - existing.ageMs > startedAt) {
      return false;
    }
  }
  return write(userId, snapshot);
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
  writeIfFresher: writeIfFresher,
  clear: clear,
  SNAPSHOT_MAX_AGE_MS: SNAPSHOT_MAX_AGE_MS,
};
