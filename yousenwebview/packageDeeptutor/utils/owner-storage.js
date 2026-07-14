// 可丢弃的本机缓存必须绑定 canonical user；业务真相仍只在服务端。
function _text(value) {
  return String(value || "").trim();
}

function keyFor(baseKey, userId) {
  var base = _text(baseKey);
  var ownerId = _text(userId);
  return base && ownerId ? base + ":" + encodeURIComponent(ownerId) : "";
}

function read(baseKey, userId) {
  var ownerId = _text(userId);
  var key = keyFor(baseKey, ownerId);
  if (!key || typeof wx === "undefined" || typeof wx.getStorageSync !== "function") return null;
  try {
    var envelope = wx.getStorageSync(key);
    if (!envelope || typeof envelope !== "object" || envelope.ownerId !== ownerId) return null;
    return envelope.value === undefined ? null : envelope.value;
  } catch (_) {
    return null;
  }
}

function write(baseKey, userId, value) {
  var ownerId = _text(userId);
  var key = keyFor(baseKey, ownerId);
  if (!key || typeof wx === "undefined" || typeof wx.setStorageSync !== "function") return false;
  try {
    wx.setStorageSync(key, { ownerId: ownerId, value: value });
    return true;
  } catch (_) {
    return false;
  }
}

function remove(baseKey, userId) {
  var key = keyFor(baseKey, userId);
  if (!key || typeof wx === "undefined" || typeof wx.removeStorageSync !== "function") return false;
  try {
    wx.removeStorageSync(key);
    return true;
  } catch (_) {
    return false;
  }
}

module.exports = { keyFor: keyFor, read: read, write: write, remove: remove };
