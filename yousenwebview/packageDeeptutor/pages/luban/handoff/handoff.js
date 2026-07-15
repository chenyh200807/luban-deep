// 鲁班学习双轮 · 交接时刻（spike 形态）
// 兼容入口不接收 query 里的完成事实。canonical receipt 留在 retest 页渲染，
// 此页只提供中性导航，避免 URL 参数伪造“已完成/已安排提醒”。
//
// 埋点走 register-before-use catalog（product_behavior_catalog.py D15 登记，
// 白名单外事件名会被 ingest 拒收，故不用任务稿的 luban_* 自由名）：
// - 交接曝光 = handoff_rendered（module=learning, action=render,
//   object_type=station, object_id=pack_id）
const route = require("../../../utils/route");
const telemetry = require("../../../utils/surface-telemetry");
const helpers = require("../../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: true,
    packId: "",
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
        url: route.lubanTeachingPoints(),
      });
    }
  },

  onMistakeBankTap() {
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({ url: route.lubanErrorbank() });
    }
  },
});
