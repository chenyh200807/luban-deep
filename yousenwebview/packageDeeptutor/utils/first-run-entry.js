// 首跑剧本入口路由（登录/注册后的单一出口 _reLaunchAfterAuth 调用）。
// 新用户判据 v1 = 本机未完成过剧本 且 账号零会话历史（覆盖注册后零消息的存量用户）。
// 任何 API 失败/超时 fail-open 直进原目标，绝不把用户挡在登录后。
var api = require("./api");
var route = require("./route");

var DONE_KEY = "deeptutor_first_run_done_v1";

function reLaunchAfterAuth(targetUrl) {
  var fallbackUrl = targetUrl || route.resolve(route.chat());
  var done = null;
  try {
    done = wx.getStorageSync(DONE_KEY);
  } catch (e) {}
  if (done && done.at) {
    wx.reLaunch({ url: fallbackUrl });
    return;
  }
  var settled = false;
  var timer = setTimeout(function () {
    if (settled) return;
    settled = true;
    wx.reLaunch({ url: fallbackUrl });
  }, 4000);
  api
    .getConversations(false)
    .then(function (resp) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      var inner = (resp && (resp.data || resp)) || {};
      var list =
        inner.conversations || inner.items || inner.list || (Array.isArray(inner) ? inner : []);
      if (Array.isArray(list) && list.length === 0) {
        wx.reLaunch({ url: route.resolve("pages/first-run/first-run") });
      } else {
        wx.reLaunch({ url: fallbackUrl });
      }
    })
    .catch(function () {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      wx.reLaunch({ url: fallbackUrl });
    });
}

module.exports = {
  reLaunchAfterAuth: reLaunchAfterAuth,
  DONE_KEY: DONE_KEY,
};
