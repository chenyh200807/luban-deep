// 首次体验本地 UI 状态。canonical 完成事实只在服务端 Learner State；
// DONE_KEY 仅缓存展示，checkpoint/pending 必须按 canonical user 隔离。
var route = require("./route");
var ownerStorage = require("./owner-storage");

var DONE_KEY = "deeptutor_first_run_done_v1";
var CHECKPOINT_KEY = "deeptutor_first_run_checkpoint_v1";
var PENDING_SYNC_KEY = "deeptutor_first_run_pending_sync_v1";

function isFirstRunDone(userId) {
  var done = ownerStorage.read(DONE_KEY, userId);
  return !!(done && done.at);
}

function readCheckpoint(userId) {
  var value = ownerStorage.read(CHECKPOINT_KEY, userId);
  return value ? value.payload || null : null;
}

function writeCheckpoint(userId, payload) {
  ownerStorage.write(CHECKPOINT_KEY, userId, { payload: payload || {}, at: Date.now() });
}

function clearCheckpoint(userId) {
  ownerStorage.remove(CHECKPOINT_KEY, userId);
}

function readPendingSync(userId) {
  var value = ownerStorage.read(PENDING_SYNC_KEY, userId);
  return value ? value.payload || null : null;
}

function savePendingSync(userId, payload) {
  ownerStorage.write(PENDING_SYNC_KEY, userId, { payload: payload || {}, at: Date.now() });
}

function clearPendingSync(userId) {
  ownerStorage.remove(PENDING_SYNC_KEY, userId);
}

function markDone(userId, payload) {
  ownerStorage.write(DONE_KEY, userId, {
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
