// 鲁班学习双轮 · 学习 tab 首页（第10轮 10a 宣纸驾驶舱 / 10b 夜宣纸）
// 只读投影：拉 /api/v1/luban/lessons 渲染下一站卡 + 路线地图，点进站点页。
// 零学习证据写入（学习证据归 learner_signal / 判分链路，本页不碰）。
// 前端不算分不造数：
// - exam_date 未接线（T5），距考卡只显示「设置考试日期 →」占位深链我的 tab；
// - 无完成态数据，下一站 = 列表第一个站；地图绿灯站 = lessons 全量；
// - manifest 外 slot 诚实标注「即将开通」，不装全。
const api = require("../../../utils/api");
const auth = require("../../../utils/auth");
const helpers = require("../../../utils/helpers");
const routeUtil = require("../../../utils/route");
const runtime = require("../../../utils/runtime");

// 路线总站数权威 = 后端 total_registered（manifest 注册包数）；
// 后端未供给（0/缺失）时隐藏总数与"即将开通"slot——禁前端硬编码第二套总量（Codex 对抗#5）。

Page({
  data: {
    // 品牌行与原生胶囊按钮组同一水平线（10a/10b 顶部构图）
    brandTop: 0,
    brandHeight: 32,
    isDark: true,
    loading: true,
    errorText: "",
    lessons: [],
    // ── 展示派生（均由 lessons 列表长度算出，不造数）──
    lessonCount: 0,
    totalStations: 0,
    routePercent: 0,
    nextLesson: null,
    nextOrdinal: 1,
    // exam_date 派生(profile read model, §5.1 "知道你考试日期"): "" = 未设置显示深链
    examDaysLeft: "",
    mapScrollId: "",
  },

  onLoad() {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var statusBarHeight = info.statusBarHeight || 0;
    var menu =
      typeof wx !== "undefined" &&
      typeof wx.getMenuButtonBoundingClientRect === "function"
        ? wx.getMenuButtonBoundingClientRect()
        : null;
    this.setData({
      brandTop: menu && menu.top ? menu.top : statusBarHeight + 6,
      brandHeight: menu && menu.height ? menu.height : 32,
      isDark: helpers.isDark(),
    });
    // 受保护请求前显式判登录：未登录带 returnTo 回跳本页（Codex 对抗#4）
    if (!auth.isLoggedIn()) {
      runtime.redirectToLogin(routeUtil.lubanStations());
      return;
    }
    this._loadLessons();
    this._loadExamCountdown();
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
    var dataset =
      event && event.currentTarget && event.currentTarget.dataset
        ? event.currentTarget.dataset
        : {};
    var packId = dataset.packId || "";
    if (!packId) return;
    // tier 透传（practice=半写档 / lesson=轻练先讲懂）；station 页当前从讲懂幕
    // 起步、暂不消费该参数——接口先行，档位深链归 station 页接线。
    var tier = dataset.tier ? String(dataset.tier) : "";
    if (typeof wx !== "undefined" && wx.navigateTo) {
      wx.navigateTo({
        url:
          "/packageDeeptutor/pages/luban/station/station?pack_id=" +
          encodeURIComponent(String(packId)) +
          (tier ? "&tier=" + encodeURIComponent(tier) : ""),
      });
    }
  },

  // 「查看完整地图 →」：滑动路线横滑区到末尾「完整路线」卡（当前无独立地图页）
  scrollMapToEnd() {
    var that = this;
    this.setData({ mapScrollId: "" }, function () {
      that.setData({ mapScrollId: "lb-map-end" });
    });
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

  // 距考天数 = profile.exam_date 纯展示派生(服务端已校验 YYYY-MM-DD, T5 已接写侧)
  _loadExamCountdown() {
    var that = this;
    return api
      .getUserInfo()
      .then(function (resp) {
        var info = api.unwrapResponse(resp) || {};
        var examDate = String(info.exam_date || "").trim();
        if (!examDate) return;
        var target = new Date(examDate + "T00:00:00+08:00").getTime();
        if (isNaN(target)) return;
        var days = Math.ceil((target - Date.now()) / 86400000);
        if (days >= 0) that.setData({ examDaysLeft: String(days) });
      })
      .catch(function () {});
  },

  _loadLessons() {
    var that = this;
    return api
      .getLubanLessons()
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var lessons = Array.isArray(body.lessons) ? body.lessons : [];
        var count = lessons.length;
        var total = parseInt(body.total_registered, 10) || 0;
        var lit = total > 0 ? Math.min(count, total) : count;
        that.setData({
          lessons: lessons,
          lessonCount: count,
          totalStations: total,
          routePercent: total > 0 ? Math.round((lit / total) * 100) : 0,
          // 下一站 = 考频优先第一站(服务端已按 registry_slot 排序, §5.1 冷启动
          // 退化为考频/priority——推荐理由可验证不编造); 无完成态数据暂不跳过已学站
          nextLesson: count ? lessons[0] : null,
          nextOrdinal: count && lessons[0].registry_slot ? lessons[0].registry_slot : 1,
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
