// 鲁班学习双轮 · 交接时刻（spike 形态）
// 用户情绪最高点：只在这里请求「明天换皮复测」订阅授权（subscribe-message 约束）。
// granted → toast「明天见」；red_dot → 页内小红点提示，不弹窗不重试。
// 零学习证据写入：只 telemetry + 本地 due 标记（红点渲染的客户端半边）。
//
// 埋点走 register-before-use catalog（product_behavior_catalog.py D15 登记，
// 白名单外事件名会被 ingest 拒收，故不用任务稿的 luban_* 自由名）：
// - 交接曝光 = handoff_rendered（module=learning, action=render,
//   object_type=station, object_id=pack_id）
// - 订阅授权结果 = subscribe_prompt_result（result=granted|red_dot）
const route = require("../../../utils/route");
const telemetry = require("../../../utils/surface-telemetry");
const subscribeMessage = require("../../../utils/subscribe-message");
const helpers = require("../../../utils/helpers");

function tomorrowDateString() {
  var d = new Date(Date.now() + 24 * 60 * 60 * 1000);
  var month = ("0" + (d.getMonth() + 1)).slice(-2);
  var day = ("0" + d.getDate()).slice(-2);
  return d.getFullYear() + "-" + month + "-" + day;
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: true,
    packId: "",
    remindRequested: false,
    showRedDotHint: false,
  },

  onLoad(query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var statusBarHeight = info.statusBarHeight || 0;
    var packId = String((query && query.pack_id) || "").trim();
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
      isDark: helpers.isDark(),
      packId: packId,
    });
    // 交接曝光（任务稿 luban_handoff_shown 的登记名）
    telemetry.trackProductBehavior("handoff_rendered", {
      module: "learning",
      action: "render",
      objectType: "station",
      objectId: packId,
    });
  },

  goBack() {
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url: "/packageDeeptutor/pages/luban/stations/stations",
      });
    }
  },

  // 按钮①「明天提醒我」——requestNextDayRetestAuthorization 永不 reject
  onRemindTap() {
    var that = this;
    if (this.data.remindRequested) return;
    this.setData({ remindRequested: true });
    subscribeMessage.requestNextDayRetestAuthorization().then(function (res) {
      var status = (res && res.status) || "red_dot";
      // 订阅授权结果（任务稿 luban_subscribe_result 的登记名）
      telemetry.trackProductBehavior("subscribe_prompt_result", {
        module: "learning",
        action: "complete",
        objectType: "station",
        objectId: that.data.packId,
        result: status,
      });
      if (status === "granted") {
        if (typeof wx !== "undefined" && wx.showToast) {
          wx.showToast({ title: "明天见", icon: "success" });
        }
      } else {
        // red_dot 降级：页内提示，不弹窗不重试
        that.setData({ showRedDotHint: true });
      }
      that._markRetestDue();
    });
  },

  onMistakeBankTap() {
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({ url: route.mistakeBook() });
    }
  },

  _markRetestDue() {
    if (!this.data.packId) return;
    if (typeof wx !== "undefined" && typeof wx.setStorageSync === "function") {
      try {
        wx.setStorageSync(
          "luban_retest_due_" + this.data.packId,
          tomorrowDateString(),
        );
      } catch (_err) {}
    }
  },
});
