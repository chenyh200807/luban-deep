// 首次体验本地 UI 状态。canonical 完成事实只在服务端 Learner State；
// DONE_KEY 仅缓存展示，checkpoint/pending 必须按 canonical user 隔离。
var route = require("./route");

var DONE_KEY = "deeptutor_first_run_done_v1";
var CHECKPOINT_KEY = "deeptutor_first_run_checkpoint_v1";
var PENDING_SYNC_KEY = "deeptutor_first_run_pending_sync_v1";

function _get(key) {
  try { return wx.getStorageSync(key) || null; } catch (_e) { return null; }
}

function _set(key, value) {
  try { wx.setStorageSync(key, value); } catch (_e) {}
}

function _remove(key) {
  try { wx.removeStorageSync(key); } catch (_e) {}
}

function _owned(record, userId) {
  var expected = String(userId || "").trim();
  return !!(record && expected && String(record.userId || "").trim() === expected);
}

function isFirstRunDone(userId) {
  var done = _get(DONE_KEY);
  if (!userId) return !!(done && done.at);
  return _owned(done, userId) && !!done.at;
}

function readCheckpoint(userId) {
  var value = _get(CHECKPOINT_KEY);
  return _owned(value, userId) ? value.payload || null : null;
}

function writeCheckpoint(userId, payload) {
  _set(CHECKPOINT_KEY, { userId: String(userId || ""), payload: payload || {}, at: Date.now() });
}

function clearCheckpoint(userId) {
  if (!userId || _owned(_get(CHECKPOINT_KEY), userId)) _remove(CHECKPOINT_KEY);
}

function readPendingSync(userId) {
  var value = _get(PENDING_SYNC_KEY);
  return _owned(value, userId) ? value.payload || null : null;
}

function savePendingSync(userId, payload) {
  _set(PENDING_SYNC_KEY, { userId: String(userId || ""), payload: payload || {}, at: Date.now() });
}

function clearPendingSync(userId) {
  if (!userId || _owned(_get(PENDING_SYNC_KEY), userId)) _remove(PENDING_SYNC_KEY);
}

function markDone(userId, payload) {
  _set(DONE_KEY, {
    userId: String(userId || ""),
    completionId: String((payload && payload.completion_id) || ""),
    scriptVersion: String((payload && payload.script_version) || ""),
    at: Date.now(),
  });
}

function getState(userId) {
  var pending = readPendingSync(userId);
  if (pending) return { state: "syncing", checkpoint: null, pending: pending };
  var checkpoint = readCheckpoint(userId);
  if (checkpoint) return { state: "resume", checkpoint: checkpoint, pending: null };
  if (isFirstRunDone(userId)) return { state: "hidden", checkpoint: null, pending: null };
  return { state: "new", checkpoint: null, pending: null };
}

// opts = { isNewAccount, hasDeepLink }。
function reLaunchAfterAuth(target, opts) {
  opts = opts || {};
  if (opts.isNewAccount && !opts.hasDeepLink) {
    wx.reLaunch({ url: route.resolve("pages/learn/learn") });
    return;
  }
  wx.reLaunch({ url: target });
}

module.exports = {
  reLaunchAfterAuth: reLaunchAfterAuth,
  isFirstRunDone: isFirstRunDone,
  getState: getState,
  readCheckpoint: readCheckpoint,
  writeCheckpoint: writeCheckpoint,
  clearCheckpoint: clearCheckpoint,
  readPendingSync: readPendingSync,
  savePendingSync: savePendingSync,
  clearPendingSync: clearPendingSync,
  markDone: markDone,
  DONE_KEY: DONE_KEY,
  CHECKPOINT_KEY: CHECKPOINT_KEY,
  PENDING_SYNC_KEY: PENDING_SYNC_KEY,
};
