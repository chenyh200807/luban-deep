// 首跑剧本入口路由（登录/注册后的落地判定）。
// 新用户判据 = 调用方显式传入 isNewAccount（仅注册创建成功的站点为 true），
// 且落地是默认页（无深链 returnTo）、本机未完成过剧本。纯本地判据：无网络、非阻塞。
// 修复：不再用 getConversations——以免 (a) 阻塞老用户登录 (b) 覆盖深链/双轮落地
// (c) 归档全部会话被误判为新用户。深链/双轮 target 一律 honor，只可能改道默认 chat 落地。
var route = require("./route");

var DONE_KEY = "deeptutor_first_run_done_v1";

function isFirstRunDone() {
  try {
    var d = wx.getStorageSync(DONE_KEY);
    return !!(d && d.at);
  } catch (e) {
    return false;
  }
}

// opts = { isNewAccount, hasDeepLink }。
function reLaunchAfterAuth(target, opts) {
  opts = opts || {};
  if (opts.isNewAccount && !opts.hasDeepLink && !isFirstRunDone()) {
    wx.reLaunch({ url: route.resolve("pages/first-run/first-run") });
    return;
  }
  wx.reLaunch({ url: target });
}

module.exports = {
  reLaunchAfterAuth: reLaunchAfterAuth,
  isFirstRunDone: isFirstRunDone,
  DONE_KEY: DONE_KEY,
};
