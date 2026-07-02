// 订阅消息授权 helper（双轮设计 v3.2 §9-D12 的客户端半边）。
//
// 约束：
// - 授权请求只在「交接时刻」调用（用户情绪最高点），绝不在冷启动/onShow 弹。
// - tmplIds 唯一来源 = 本文件 TEMPLATE_IDS（owner 后台申请到模板后填入，
//   与服务端 env WECHAT_SUBSCRIBE_TMPL_* 保持同值）。
// - 一切失败（未配置/用户拒绝/API 报错/环境不支持）都退化为
//   { status: "red_dot" }——调用方据此渲染 App 内红点 + 英雄位文案，不硬弹不重试。
var logger = require("./logger");

// owner 申请到模板 ID 后填入；空字符串 = 链路未建成，一律红点降级
var TEMPLATE_IDS = {
  nextDayRetest: "",
};

function redDot(reason) {
  return { status: "red_dot", reason: reason || "" };
}

// 在交接时刻调用：请求「明天换皮复测」推送授权。
// 返回 Promise<{status: "granted"|"red_dot", reason}>，永不 reject。
function requestNextDayRetestAuthorization() {
  var tmplId = String(TEMPLATE_IDS.nextDayRetest || "").trim();
  if (!tmplId) {
    return Promise.resolve(redDot("template_not_configured"));
  }
  if (typeof wx === "undefined" || !wx.requestSubscribeMessage) {
    return Promise.resolve(redDot("api_unavailable"));
  }
  return new Promise(function (resolve) {
    wx.requestSubscribeMessage({
      tmplIds: [tmplId],
      success: function (res) {
        if (res && res[tmplId] === "accept") {
          resolve({ status: "granted", tmplId: tmplId });
          return;
        }
        resolve(redDot("user_" + String((res && res[tmplId]) || "reject")));
      },
      fail: function (err) {
        logger.warn &&
          logger.warn("subscribe-message", "requestSubscribeMessage fail", err);
        resolve(redDot("request_failed"));
      },
    });
  });
}

module.exports = {
  TEMPLATE_IDS: TEMPLATE_IDS,
  requestNextDayRetestAuthorization: requestNextDayRetestAuthorization,
};
