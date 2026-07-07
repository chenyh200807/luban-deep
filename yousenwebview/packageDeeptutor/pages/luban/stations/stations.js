// 鲁班学习双轮 · 站点列表（spike 形态）
// 只读投影：拉 /api/v1/luban/lessons 渲染绿灯站点卡，点进站点页。
// 零学习证据写入（学习证据归 learner_signal / 判分链路，本页不碰）。
const api = require("../../../utils/api");
const helpers = require("../../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: true,
    loading: true,
    errorText: "",
    lessons: [],
  },

  onLoad() {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var statusBarHeight = info.statusBarHeight || 0;
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + 48,
      isDark: helpers.isDark(),
    });
    this._loadLessons();
  },

  onPullDownRefresh() {
    this._loadLessons().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) {
        wx.stopPullDownRefresh();
      }
    });
  },

  retry() {
    this.setData({ loading: true, errorText: "" });
    this._loadLessons();
  },

  goBack() {
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) {
      wx.navigateBack();
    }
  },

  openStation(event) {
    var packId =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset.packId
        : "";
    if (!packId) return;
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url:
          "/packageDeeptutor/pages/luban/station/station?pack_id=" +
          encodeURIComponent(String(packId)),
      });
    }
  },

  _loadLessons() {
    var that = this;
    return api
      .getLubanLessons()
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var lessons = Array.isArray(body.lessons) ? body.lessons : [];
        that.setData({ lessons: lessons, loading: false, errorText: "" });
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          errorText: api.describeRequestError(
            err,
            "站点列表加载失败，请稍后重试",
          ),
        });
      });
  },
});
