// 复习 tab 首页（T0 最小占位壳）
// T2 会在此落到期推送 / 自主检索 / 考点卡 / 错因银行；本页只保证五 tab 可导航。
// 零学习证据写入；不做任何数据拉取。
var helpers = require("../../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    isDark: true,
  },

  onLoad: function () {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    this.setData({
      statusBarHeight: info.statusBarHeight || 0,
    });
  },

  onShow: function () {
    this.setData({ isDark: helpers.isDark() });
    // 高亮以壳内路由判定为权威，序号仅兜底（review = 1）
    helpers.syncTabBar(this, 1);
  },
});
