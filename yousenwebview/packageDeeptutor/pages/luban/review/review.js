// 复习 tab 首页（第10轮 10c 回炉驾驶舱）
// 只读投影，前端不算分不造数：
// - 到期 = /api/v1/luban/lessons/{pack}/retest-items 有数据的站
//   （服务端确定性排定，本页零调度逻辑，不自算间隔）；
// - 错因银行计数/错因聚合 = 云端错题集 read model
//   （错因名走 labelFor 投影 ERROR_CODE_REGISTRY，禁第二套错因分类）；
// - 考点卡区后端未供给字段 → 「即将开通」占位（禁前端自造卡文案）；
// - 自主检索 = 纯前端过滤已加载数据（按母题=点亮站 / 按错因=错题错因聚合）。
// 零学习证据写入（学习证据归 learner_signal / 判分链路，本页不碰）。
var api = require("../../../utils/api");
var auth = require("../../../utils/auth");
var helpers = require("../../../utils/helpers");
var route = require("../../../utils/route");
var runtime = require("../../../utils/runtime");
var mistakeBookViewModel = require("../../../utils/mistake-book-view-model");

// 到期数据 = /api/v1/luban/review-due(revalidation_queue 投影), 前端零探测零调度。

Page({
  data: {
    statusBarHeight: 0,
    isDark: true,
    loading: true,
    errorText: "",
    dueNotice: "",
    lessons: [],
    dueEntries: [],
    dueCount: 0,
    learnedCount: 0,
    dueItemTotal: 0,
    duePercent: 0,
    // true = 有站点探测失败或点亮站超出探测上限——到期结论不完整，
    // 禁展示确定性"今天没有到期"（诚实降级为弱化文案）。
    dueUncertain: false,
    firstDue: null,
    searchMode: "pack",
    errorBars: [],
    // -1 = 计数未取到（错因银行入口降级为无计数，不造数）
    mistakeActiveCount: -1,
  },

  onLoad: function () {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    this.setData({
      statusBarHeight: info.statusBarHeight || 0,
      isDark: helpers.isDark(),
    });
    // 受保护请求前显式判登录：未登录带 returnTo 回跳本页，
    // 避免 api.js 401 兜底 redirectToLogin() 丢目标页（登录后落回 chat）。
    if (!auth.isLoggedIn()) {
      runtime.redirectToLogin(route.lubanReview());
      return;
    }
    this._loadAll();
  },

  onShow: function () {
    this.setData({ isDark: helpers.isDark() });
    // 高亮以壳内路由判定为权威，序号仅兜底（review = 1）
    helpers.syncTabBar(this, 1);
  },

  onPullDownRefresh: function () {
    this._loadAll().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) {
        wx.stopPullDownRefresh();
      }
    });
  },

  retry: function () {
    this._loadAll();
  },

  // 空态深链：回炉的都是学过的，先去学习 tab 点亮第一站（D1 空态铁律）
  goLearn: function () {
    if (typeof wx === "undefined" || !wx.redirectTo) return;
    wx.redirectTo({
      url: route.lubanStations(),
      fail: function () {
        if (wx.reLaunch) {
          wx.reLaunch({ url: route.lubanStations() });
        }
      },
    });
  },

  // 「开始回炉」= 进第一个到期站的换皮复测
  startDue: function () {
    var firstDue = this.data.firstDue;
    if (!firstDue) return;
    this._openRetestByPackId(firstDue.packId);
  },

  openRetest: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    this._openRetestByPackId(dataset.packId);
  },

  // 错因银行归位入口（唯一入口在本 tab，不再挂别处 tab 位）
  openMistakeBook: function () {
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({ url: route.mistakeBook() });
  },

  setSearchMode: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var mode = dataset.mode === "error" ? "error" : "pack";
    if (mode === this.data.searchMode) return;
    this.setData({ searchMode: mode });
  },

  _openRetestByPackId: function (packId) {
    var clean = String(packId || "").trim();
    if (!clean) return;
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({
      url:
        "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
        encodeURIComponent(clean),
    });
  },

  _loadAll: function () {
    this.setData({ loading: true, errorText: "", dueNotice: "", dueUncertain: false });
    return Promise.all([this._loadDue(), this._loadMistakeBank()]);
  },

  _loadDue: function () {
    // 到期语义唯一权威 = 服务端 revalidation_queue 投影(/luban/review-due)。
    // 旧版前端 N+1 探测(有变体池=到期, 六站天天全到期)已废——那是假引擎感。
    var that = this;
    return Promise.all([api.getLubanLessons(), api.getLubanReviewDue()])
      .then(function (results) {
        var lessonsBody = api.unwrapResponse(results[0]) || {};
        var dueBody = api.unwrapResponse(results[1]) || {};
        var lessons = Array.isArray(lessonsBody.lessons) ? lessonsBody.lessons : [];
        var due = Array.isArray(dueBody.due) ? dueBody.due : [];
        var learnedCount = Number(dueBody.learned_count || 0);
        var dueEntries = due.map(function (item) {
          return {
            packId: item.pack_id,
            title: item.title || item.pack_id,
            retestAvailable: !!item.retest_available,
          };
        });
        that.setData({
          lessons: lessons,
          dueEntries: dueEntries,
          dueCount: dueEntries.length,
          dueItemTotal: dueEntries.length,
          duePercent: learnedCount
            ? Math.round((dueEntries.length / learnedCount) * 100)
            : 0,
          learnedCount: learnedCount,
          dueUncertain: false,
          firstDue: dueEntries.length ? dueEntries[0] : null,
          dueNotice: "",
          loading: false,
        });
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          errorText: api.describeRequestError(
            err,
            "复习数据加载失败，请稍后重试",
          ),
        });
      });
  },

  // 错因银行入口计数 + 按错因检索的聚合（云端错题集 read model，只读）
  _loadMistakeBank: function () {
    var that = this;
    return api
      .getMistakeBook(
        { include_mastered: false },
        { suppressAuthRedirect: true },
      )
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var model = mistakeBookViewModel.buildMistakeBookViewModel(body);
        that.setData({
          mistakeActiveCount: model.activeCount,
          errorBars: model.errorBars,
        });
      })
      .catch(function () {
        // 计数拿不到时入口降级为无计数（不阻塞页面、不造数）
        that.setData({ mistakeActiveCount: -1, errorBars: [] });
      });
  },
});
