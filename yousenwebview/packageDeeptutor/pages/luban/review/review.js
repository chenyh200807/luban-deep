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

var RETEST_LIMIT = 5;
// 到期探测上限：luban_lesson_retest 限流 30 次/60s，留余量。
// 点亮站超过上限后，到期聚合应由后端供给，前端不越权补调度。
var RETEST_PROBE_MAX = 20;
// 探测并发上限：分批串行，避免瞬时打满限流窗把探测失败伪装成"无到期"。
var RETEST_PROBE_CONCURRENCY = 4;
// 探测失败/截断时的弱化文案（禁确定性"没有到期"）。
var DUE_UNCERTAIN_NOTICE = "部分站点未能检查，下拉重试";

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

  // 逐站探测 retest-items（分批串行，单批 ≤RETEST_PROBE_CONCURRENCY 并发防限流）
  _probeDueInChunks: function (targets) {
    var results = [];
    var probeOne = function (lesson) {
      return api
        .getLubanRetestItems(lesson.pack_id, RETEST_LIMIT)
        .then(function (itemsResp) {
          var itemsBody = api.unwrapResponse(itemsResp) || {};
          var items = Array.isArray(itemsBody.items) ? itemsBody.items : [];
          return { lesson: lesson, count: items.length, failed: false };
        })
        .catch(function () {
          // 单站探测失败不阻塞整页，但必须计入 dueUncertain（禁伪装成"无到期"）
          return { lesson: lesson, count: 0, failed: true };
        });
    };
    var runChunk = function (start) {
      if (start >= targets.length) return Promise.resolve(results);
      var chunk = targets
        .slice(start, start + RETEST_PROBE_CONCURRENCY)
        .map(probeOne);
      return Promise.all(chunk).then(function (part) {
        results = results.concat(part);
        return runChunk(start + RETEST_PROBE_CONCURRENCY);
      });
    };
    return runChunk(0);
  },

  // 到期推送区：逐站探测 retest-items 有无数据（有 = 今日到期）
  _loadDue: function () {
    var that = this;
    return api
      .getLubanLessons()
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        var lessons = Array.isArray(body.lessons) ? body.lessons : [];
        if (!lessons.length) {
          that.setData({
            lessons: [],
            dueEntries: [],
            dueCount: 0,
            dueItemTotal: 0,
            duePercent: 0,
            dueUncertain: false,
            firstDue: null,
            loading: false,
          });
          return;
        }
        var truncated = lessons.length > RETEST_PROBE_MAX;
        var targets = lessons.slice(0, RETEST_PROBE_MAX);
        return that._probeDueInChunks(targets).then(function (results) {
          var dueEntries = [];
          var dueItemTotal = 0;
          var failedCount = 0;
          results.forEach(function (result) {
            if (result.failed) {
              failedCount += 1;
              return;
            }
            if (result.count > 0) {
              dueEntries.push({
                packId: result.lesson.pack_id,
                title: result.lesson.title || result.lesson.pack_id,
                count: result.count,
              });
              dueItemTotal += result.count;
            }
          });
          // 有失败或截断 = 到期结论不完整：禁展示确定性"没有到期"
          var dueUncertain = failedCount > 0 || truncated;
          that.setData({
            lessons: lessons,
            dueEntries: dueEntries,
            dueCount: dueEntries.length,
            dueItemTotal: dueItemTotal,
            duePercent: lessons.length
              ? Math.round((dueEntries.length / lessons.length) * 100)
              : 0,
            dueUncertain: dueUncertain,
            firstDue: dueEntries.length ? dueEntries[0] : null,
            dueNotice: dueUncertain ? DUE_UNCERTAIN_NOTICE : "",
            loading: false,
          });
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
