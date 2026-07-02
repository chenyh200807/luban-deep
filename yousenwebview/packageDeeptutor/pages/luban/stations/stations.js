// 鲁班学习双轮 · 学习 tab 首页（第10轮 10a 宣纸驾驶舱 / 10b 夜宣纸）
// 只读投影：拉 /api/v1/luban/lessons 渲染下一站卡 + 路线地图，点进站点页。
// 零学习证据写入（学习证据归 learner_signal / 判分链路，本页不碰）。
// 前端不算分不造数：
// - exam_date 未接线（T5），距考卡只显示「设置考试日期 →」占位深链我的 tab；
// - 无完成态数据，下一站 = 列表第一个站；地图绿灯站 = lessons 全量；
// - manifest 外 slot 诚实标注「即将开通」，不装全。
const api = require("../../../utils/api");
const helpers = require("../../../utils/helpers");

// 路线总站数（第10轮定稿口径「已点亮 N/40 站」）
var TOTAL_STATIONS = 40;

Page({
  data: {
    statusBarHeight: 0,
    isDark: true,
    loading: true,
    errorText: "",
    lessons: [],
    // ── 展示派生（均由 lessons 列表长度算出，不造数）──
    lessonCount: 0,
    totalStations: TOTAL_STATIONS,
    routePercent: 0,
    nextLesson: null,
    upcomingSlots: [],
  },

  onLoad() {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    this.setData({
      statusBarHeight: info.statusBarHeight || 0,
      isDark: helpers.isDark(),
    });
    this._loadLessons();
  },

  onShow() {
    this.setData({ isDark: helpers.isDark() });
    // 高亮以壳内路由判定为权威，序号仅兜底（learn = 0）
    helpers.syncTabBar(this, 0);
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

  // 距考卡占位深链：exam_date 设置在「我的」tab（T5 接线后本卡换真实天数）
  goProfile() {
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({
      url: "/packageDeeptutor/pages/profile/profile",
      fail: function () {
        if (wx.redirectTo) {
          wx.redirectTo({ url: "/packageDeeptutor/pages/profile/profile" });
        }
      },
    });
  },

  // 复习到期 chip：纯跳转复习 tab，不做任何到期逻辑（逻辑归 T2/后端）
  goReview() {
    if (typeof wx === "undefined" || !wx.redirectTo) return;
    wx.redirectTo({
      url: "/packageDeeptutor/pages/luban/review/review",
      fail: function () {
        if (wx.reLaunch) {
          wx.reLaunch({ url: "/packageDeeptutor/pages/luban/review/review" });
        }
      },
    });
  },

  _loadLessons() {
    var that = this;
    return api
      .getLubanLessons()
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var lessons = Array.isArray(body.lessons) ? body.lessons : [];
        var count = lessons.length;
        var lit = Math.min(count, TOTAL_STATIONS);
        var upcoming = [];
        for (var i = count; i < TOTAL_STATIONS; i++) {
          upcoming.push(i + 1);
        }
        that.setData({
          lessons: lessons,
          lessonCount: count,
          routePercent: Math.round((lit / TOTAL_STATIONS) * 100),
          nextLesson: count ? lessons[0] : null,
          upcomingSlots: upcoming,
          loading: false,
          errorText: "",
        });
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
