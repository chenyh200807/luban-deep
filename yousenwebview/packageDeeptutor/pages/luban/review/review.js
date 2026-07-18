// 复习页（第10轮 10c 回炉屏）
// 只读投影，前端不算分不造数：
// - 到期 = /api/v1/luban/review-due（revalidation_queue 服务端投影，
//   本页零调度逻辑、零 N+1 探测、不自算间隔）；
// - 变体池空的站 fail-closed 隐藏「换皮」承诺句（review-view-model 单一判定点），
//   回炉动作降级为回站重看；
// - 错因银行计数/错因聚合 = 云端错题集 read model（只读）；
// - 考点卡库 = /api/v1/luban/concept-cards 只读投影（张数=signed 卡池真值；
//   旗标关/请求失败/零签发池 → 「即将开通」占位，禁前端自造卡数与文案）；
// - 自主检索 = 纯前端过滤已加载数据（按母题=点亮站 / 按错因=错题错因聚合）。
// 零学习证据写入（学习证据归 learner_signal / 判分链路，本页不碰）。
var api = require("../../../utils/api");
var helpers = require("../../../utils/helpers");
var auth = require("../../../utils/auth");
var route = require("../../../utils/route");
var runtime = require("../../../utils/runtime");
var mistakeBookViewModel = require("../../../utils/mistake-book-view-model");
var reviewViewModel = require("../../../utils/review-view-model");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false, // 第10版主色=宣纸亮(与 stations/learn 同口径)
    loading: true,
    errorText: "",
    vm: null, // review-view-model 输出
    searchMode: "pack",
  },

  onLoad: function () {
    this._hasShown = false;
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48, isDark: helpers.isDarkOr("light") });
    // 受保护请求前显式判登录：未登录带 returnTo 回跳本页，
    // 避免 api.js 401 兜底 redirectToLogin() 丢目标页（登录后落回 chat）。
    if (!auth.isLoggedIn()) {
      runtime.redirectToLogin(route.lubanReview());
      return;
    }
    this._loadAll();
  },

  onShow: function () {
    // 旧 URL 只保留历史深链兼容；复习已并入学习任务，不能再占用历史 tab。
    if (this._hasShown && !this.data.loading && auth.isLoggedIn()) {
      this._loadAll();
    }
    this._hasShown = true;
  },

  onPullDownRefresh: function () {
    this._loadAll().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) {
        wx.stopPullDownRefresh();
      }
    });
  },

  goBack: function () {
    if (typeof wx === "undefined") return;
    var pages = typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (pages.length > 1 && wx.navigateBack) {
      wx.navigateBack();
      return;
    }
    if (wx.redirectTo) {
      wx.redirectTo({
        url: route.learn(),
        fail: function () {
          if (wx.reLaunch) wx.reLaunch({ url: route.learn() });
        },
      });
    }
  },

  retry: function () {
    this._loadAll();
  },

  // 空态深链：回炉的都是学过的，先去学习页点亮第一站（D1 空态铁律）
  goLearn: function () {
    if (typeof wx === "undefined" || !wx.redirectTo) return;
    wx.redirectTo({
      url: route.learn(),
      fail: function () {
        if (wx.reLaunch) {
          wx.reLaunch({ url: route.learn() });
        }
      },
    });
  },

  // 「开始回炉」= 进第一个到期站（有变体池→换皮复测；无池→回站重看, fail-closed）
  startDue: function () {
    var vm = this.data.vm;
    if (!vm || !vm.firstDue) return;
    this._openDueEntry(vm.firstDue);
  },

  openDueEntry: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var vm = this.data.vm;
    var entries = (vm && vm.dueEntries) || [];
    for (var i = 0; i < entries.length; i++) {
      if (entries[i].packId === dataset.packId) {
        this._openDueEntry(entries[i]);
        return;
      }
    }
  },

  // 自主检索(按母题): 回站重看——lessons 列表无变体池信息, 诚实默认=站页
  // (站内自带复测入口, 有池才见), 不盲跳 retest 撞 404。
  openStation: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var clean = String(dataset.packId || "").trim();
    if (!clean) return;
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({
      url:
        "/packageDeeptutor/pages/luban/station/station?pack_id=" +
        encodeURIComponent(clean),
    });
  },

  // 错因银行归位入口（唯一入口在复习页，不再挂别处 tab 位）
  // 复习二期: 指向新错因银行列表页(四段瀑布详情), 旧 mistake-book 页保留给其他深链
  openMistakeBook: function () {
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({ url: route.lubanErrorbank() });
  },

  // 到期清单行 → 实务闯关(回忆→半写→核对); vm 单一判定点 gauntletAvailable
  // (变体池 fail-closed)控制入口渲染, 本 handler 只路由
  openGauntlet: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var vm = this.data.vm;
    var entries = (vm && vm.dueEntries) || [];
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (entry.packId !== dataset.packId) continue;
      if (!entry.gauntletAvailable) return;
      if (typeof wx === "undefined" || !wx.navigateTo) return;
      wx.navigateTo({
        url: route.lubanGauntlet({ pack_id: entry.packId, title: entry.title }),
      });
      return;
    }
  },

  // 考点卡库入口（vm 单一判定点：signed 卡池真有卡才可点，占位态不接线）
  openConceptCards: function () {
    var vm = this.data.vm;
    if (!vm || !vm.conceptCardsAvailable) return;
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({ url: route.lubanConceptCards() });
  },

  setSearchMode: function (event) {
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var mode = dataset.mode === "error" ? "error" : "pack";
    if (mode === this.data.searchMode) return;
    this.setData({ searchMode: mode });
  },

  _openDueEntry: function (entry) {
    if (!entry || !entry.packId) return;
    if (entry.action === "retest") {
      this._openRetestByPackId(entry.packId, entry.probeId);
      return;
    }
    // 无变体池: 回站重看(不承诺换皮)
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({
      url:
        "/packageDeeptutor/pages/luban/station/station?pack_id=" +
        encodeURIComponent(entry.packId),
    });
  },

  _openRetestByPackId: function (packId, probeId) {
    var clean = String(packId || "").trim();
    if (!clean) return;
    if (typeof wx === "undefined" || !wx.navigateTo) return;
    wx.navigateTo({
      url:
        "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
        encodeURIComponent(clean) +
        "&mode=review&probe_id=" +
        encodeURIComponent(String(probeId || "")),
    });
  },

  _loadAll: function () {
    // 到期语义来自 unified learning report 的 pack_review；页面不再单独拉一份
    // learner-state 读模型。课程/卡库仍只是内容 supply join。
    var that = this;
    this.setData({ loading: true, errorText: "" });
    var mistakePromise = api
      .getMistakeBook({ include_mastered: false }, { suppressAuthRedirect: true })
      .then(function (resp) {
        var body = api.unwrapResponse(resp) || {};
        return mistakeBookViewModel.buildMistakeBookViewModel(body);
      })
      .catch(function () {
        // 计数拿不到时入口降级为无计数（不阻塞页面、不造数）
        return null;
      });
    // 点亮真值 = pack_lifecycle（与学习页同一读源 getLearningReport, 单一权威）。
    // 拿不到时降级为 null——view model 不造数（既不标已点亮也不标未点亮）。
    var reportPromise = api
      .getLearningReport(100, { silent: true, suppressAuthRedirect: true })
      .then(function (resp) {
        return api.unwrapResponse(resp) || {};
      })
      .catch(function () {
        return null;
      });
    // 考点卡库张数(signed 卡池投影)——拿不到降级 null, 入口回「即将开通」占位
    var conceptCardsPromise = api
      .getLubanConceptCardLibrary({ suppressAuthRedirect: true })
      .then(function (resp) {
        return api.unwrapResponse(resp) || {};
      })
      .catch(function () {
        return null;
      });
    return Promise.all([
      api.getLubanLessons(),
      mistakePromise,
      reportPromise,
      conceptCardsPromise,
    ])
      .then(function (results) {
        var vm = reviewViewModel.buildReviewViewModel({
          lessons: api.unwrapResponse(results[0]) || {},
          reviewDue: (results[2] && results[2].pack_review) || {},
          mistakeBook: results[1],
          report: results[2],
          conceptCards: results[3],
        });
        that.setData({ vm: vm, loading: false });
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
});
