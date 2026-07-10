// 首跑剧本入口路由（计划 §3：新用户登录后的默认路径，老用户直进 chat）。
// "新用户"判据 v1 = 本机未完成过剧本 且 账号零会话历史——
// 精确覆盖目标人群（含 60% 注册后零消息的存量用户），不依赖后端新字段。
// 任何 API 失败 fail-open 直进 chat，绝不把用户挡在登录后。
var api = require("./api");

var DONE_KEY = "deeptutor_first_run_done_v1";

function goChat() {
  wx.switchTab({ url: "/pages/chat/chat" });
}

function goHomeAfterAuth() {
  var done = null;
  try {
    done = wx.getStorageSync(DONE_KEY);
  } catch (e) {}
  if (done && done.at) {
    goChat();
    return;
  }
  var settled = false;
  var timer = setTimeout(function () {
    // 历史接口超时兜底：不让新用户在登录后白屏等待
    if (settled) return;
    settled = true;
    goChat();
  }, 4000);
  api
    .getConversations(false)
    .then(function (resp) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      var inner = (resp && (resp.data || resp)) || {};
      var list = inner.conversations || inner.items || inner.list || (Array.isArray(inner) ? inner : []);
      if (Array.isArray(list) && list.length === 0) {
        wx.reLaunch({ url: "/pages/first-run/first-run" });
      } else {
        goChat();
      }
    })
    .catch(function () {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      goChat();
    });
}

module.exports = {
  goHomeAfterAuth: goHomeAfterAuth,
  DONE_KEY: DONE_KEY,
};
