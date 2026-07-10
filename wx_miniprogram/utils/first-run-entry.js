// 首跑剧本入口路由（登录/注册后的落地判定）。
// 新用户判据 = 调用方显式传入 isNewAccount（仅注册创建成功的站点为 true），
// 且本机未完成过剧本。纯本地判据：无网络、非阻塞——不再用 getConversations，
// 以免 (a) 阻塞老用户登录 (b) 覆盖深链 (c) 归档全部会话被误判为新用户。
var DONE_KEY = "deeptutor_first_run_done_v1";

function isFirstRunDone() {
  try {
    var d = wx.getStorageSync(DONE_KEY);
    return !!(d && d.at);
  } catch (e) {
    return false;
  }
}

// isNewAccount=true（刚注册创建）且未完成过剧本 → 进「第一分钟」；否则直达 chat。
function goHomeAfterAuth(isNewAccount) {
  if (isNewAccount && !isFirstRunDone()) {
    wx.reLaunch({ url: "/pages/first-run/first-run" });
    return;
  }
  wx.switchTab({ url: "/pages/chat/chat" });
}

module.exports = {
  goHomeAfterAuth: goHomeAfterAuth,
  isFirstRunDone: isFirstRunDone,
  DONE_KEY: DONE_KEY,
};
