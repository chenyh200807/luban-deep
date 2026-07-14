var CACHE_KEY_DELETED = "history_deleted_conversation_ids";
var auth = require("./auth");
var ownerStorage = require("./owner-storage");

function _ownerId() {
  return String((auth && auth.getUserId && auth.getUserId()) || "").trim();
}

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
    var raw = ownerStorage.read(CACHE_KEY_DELETED, _ownerId());
    var tombstones = _normalizeTombstones(raw);
    if (Array.isArray(raw)) ownerStorage.write(CACHE_KEY_DELETED, _ownerId(), tombstones);
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
    ownerStorage.write(CACHE_KEY_DELETED, _ownerId(), tombstones);
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
