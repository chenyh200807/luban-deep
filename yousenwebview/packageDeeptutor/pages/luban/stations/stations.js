// 鲁班学习双轮 · 提分路线(纸墨朱竹书法海报路线图,五模块第 10 轮定稿)
// 只读投影:并发拉绿灯站 + pack_lifecycle + next_step → learn-view-model 组装海报三态。
// 复用学习 home 同一 view-model(单一来源),海报组件与学习 home 课程架一致。
// 零学习证据写入(学习证据归 lesson-progress[讲懂幕] / 判分链路,本页不碰)。
const api = require("../../../utils/api");
const helpers = require("../../../utils/helpers");
const { buildLearnViewModel } = require("../../../utils/learn-view-model");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false,
    loading: true,
    errorText: "",
    posters: [],
    litCount: 0,
    packUniverse: 40,
  },

  onLoad() {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48, isDark: false /* 第10版主色=宣纸亮,默认亮色;夜宣纸暗版 wxss 仍在 */ });
    this._load();
  },

  onPullDownRefresh() {
    var that = this;
    this._load().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) wx.stopPullDownRefresh();
    });
  },

  retry() {
    this.setData({ loading: true, errorText: "" });
    this._load();
  },

  goBack() {
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && typeof wx !== "undefined" && wx.navigateBack) wx.navigateBack();
  },

  openStation(event) {
    var ds = (event && event.currentTarget && event.currentTarget.dataset) || {};
    var packId = ds.packId;
    if (!packId) return;
    if (ds.green === false) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "这一站即将开通", icon: "none" });
      return;
    }
    if (ds.cardHosted === false) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "这一站微课即将开通", icon: "none" });
      return;
    }
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url: "/packageDeeptutor/pages/luban/station/station?pack_id=" + encodeURIComponent(String(packId)),
      });
    }
  },

  _load() {
    var that = this;
    var opt = { silent: true };
    var settle = function (p) {
      return Promise.resolve(p).then(function (r) { return r; }, function () { return null; });
    };
    return Promise.all([
      settle(api.getLubanLessons(opt)),
      settle(api.getLearningReport(100, opt)),
      settle(api.getHomeDashboard(opt)),
    ]).then(function (res) {
      var lessons = api.unwrapResponse(res[0]) || {};
      var report = api.unwrapResponse(res[1]) || {};
      var homeDashboard = api.unwrapResponse(res[2]) || {};
      var vm = buildLearnViewModel({ homeDashboard: homeDashboard, report: report, lessons: lessons });
      that.setData({
        posters: vm.posters || [],
        litCount: vm.litCount || 0,
        packUniverse: vm.packUniverse || 40,
        loading: false,
        errorText: "",
      });
    });
  },
});
