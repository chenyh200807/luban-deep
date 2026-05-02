var CACHE_KEY_DELETED = "history_deleted_conversation_ids";

function _normalizeTombstones(raw) {
  var tombstones = {};
  if (Array.isArray(raw)) {
    raw.forEach(function (id) {
      var key = String(id || "").trim();
      if (key) tombstones[key] = Date.now();
    });
    return tombstones;
  }
  if (!raw || typeof raw !== "object") return tombstones;
  Object.keys(raw).forEach(function (id) {
    var key = String(id || "").trim();
    if (key) tombstones[key] = Number(raw[id]) || Date.now();
  });
  return tombstones;
}

function readDeletedConversationIds() {
  try {
    var raw = wx.getStorageSync(CACHE_KEY_DELETED);
    var tombstones = _normalizeTombstones(raw);
    if (Array.isArray(raw)) {
      wx.setStorageSync(CACHE_KEY_DELETED, tombstones);
    }
    return tombstones;
  } catch (_) {
    return {};
  }
}

function rememberDeletedConversationIds(ids) {
  var tombstones = readDeletedConversationIds();
  (ids || []).forEach(function (id) {
    var key = String(id || "").trim();
    if (key) tombstones[key] = Date.now();
  });
  try {
    wx.setStorageSync(CACHE_KEY_DELETED, tombstones);
  } catch (_) {}
  return tombstones;
}

function filterDeletedConversations(convs) {
  var tombstones = readDeletedConversationIds();
  return (Array.isArray(convs) ? convs : []).filter(function (item) {
    return !tombstones[String((item && item.id) || "").trim()];
  });
}

module.exports = {
  filterDeletedConversations: filterDeletedConversations,
  readDeletedConversationIds: readDeletedConversationIds,
  rememberDeletedConversationIds: rememberDeletedConversationIds,
};
