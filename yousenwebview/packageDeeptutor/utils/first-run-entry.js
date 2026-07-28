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

// canonical 完成事实只在服务端 Learner State（投影
// /assessment/profile → diagnostic_sources.first_run.completed）。本地 DONE_KEY
// 只是可丢弃的 UI 缓存：老用户清缓存/换设备后本地缓存丢失，getState 会重新
// 判定为 "new"，首跑门错误地重新出现、任务卡被挡。
//
// refreshFromServer 在本地无任何首跑痕迹（无 DONE / checkpoint / pending）时
// 回读一次服务端完成投影，命中则把本地 DONE 补写回来——服务端仍是唯一
// writer，本地只是缓存 rehydration。同步 getState 语义不变。
//
// fail-safe：任何缺依赖 / 未完成 / 接口失败一律维持现状（多显示一次首跑门
// 无害，首跑写回本身幂等）。本地已有 DONE/checkpoint/pending 时直接短路，
// 不打接口，避免每次冷启动都请求 /assessment/profile。
function refreshFromServer(userId, api) {
  var ownerId = String(userId || "").trim();
  var current = getState(ownerId);
  if (!ownerId || !api || typeof api.getAssessmentProfile !== "function") {
    return Promise.resolve(current);
  }
  // 本地已有权威缓存（DONE）或进行中的首跑（resume/syncing）→ 不回读。
  if (current.state !== "new") {
    return Promise.resolve(current);
  }
  return Promise.resolve(
    api.getAssessmentProfile({ silent: true, suppressAuthRedirect: true }),
  )
    .then(function (raw) {
      var profile =
        (typeof api.unwrapResponse === "function" ? api.unwrapResponse(raw) : raw) ||
        raw ||
        {};
      var sources =
        profile && typeof profile === "object" ? profile.diagnostic_sources : null;
      var firstRun =
        sources && typeof sources === "object" ? sources.first_run : null;
      if (firstRun && firstRun.completed === true) {
        markDone(ownerId, {
          completion_id: firstRun.completion_id,
          script_version: firstRun.script_version,
        });
      }
      return getState(ownerId);
    })
    .catch(function () {
      return getState(ownerId);
    });
}

// opts = { isNewAccount, hasDeepLink }。
// 新账号（且无深链）直接落首次学习旅程：注册完第一屏就是真题，不再中转学习首页
// 等用户自己发现入口。首跑没做完不需要另外落地——学习首页顶部的首跑卡会走
// getState() 的 resume 态（checkpoint 已在 first-run 页每步落盘）继续接上。
// 深链优先级不变；老用户（isNewAccount 为 false）行为完全不变。
function reLaunchAfterAuth(target, opts) {
  opts = opts || {};
  if (opts.isNewAccount && !opts.hasDeepLink) {
    wx.reLaunch({ url: route.resolve("pages/first-run/first-run") });
    return;
  }
  wx.reLaunch({ url: target });
}

module.exports = {
  reLaunchAfterAuth: reLaunchAfterAuth,
  isFirstRunDone: isFirstRunDone,
  getState: getState,
  refreshFromServer: refreshFromServer,
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
