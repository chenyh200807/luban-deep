// 学习 tab · 纸墨朱竹宣纸驾驶舱(五模块第 10 轮定稿 10a/10b)
// 只读投影:并发拉 next_step(homepage/dashboard)+ pack_lifecycle/stats(learning-report)
// + 绿灯站(luban/lessons)→ learn-view-model 组装 → setData。
// 零学习证据写入(学习证据归 lesson-progress[讲懂幕] / 判分链路)。
// 全程降级:任一 read model 字段缺(test2 后端未部署常态)不崩,走空态。
const api = require("../../utils/api");
const helpers = require("../../utils/helpers");
const { buildLearnViewModel } = require("../../utils/learn-view-model");

// H2:Long Cang 只许 CDN 子集化,禁内嵌。子集托管后填此常量;
// 空/失败 → 降级 'Kaiti SC', serif(paper-ink.wxss font-family 已兜底)。
const LONG_CANG_FONT_URL = "";

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: true,
    loading: true,
    vm: null, // learn-view-model 输出
    whyOpen: false,
  },

  onLoad() {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48, isDark: helpers.isDark() });
    this._loadLongCangFont();
    this._load();
  },

  onShow() {
    // 从站点/复习返回时刷新点亮态
    if (!this.data.loading) this._load();
  },

  onPullDownRefresh() {
    var that = this;
    this._load().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) wx.stopPullDownRefresh();
    });
  },

  // H2:CDN 子集加载,失败静默降级 Kaiti(不内嵌、不报错打断)
  _loadLongCangFont() {
    if (!LONG_CANG_FONT_URL || typeof wx === "undefined" || !wx.loadFontFace) return;
    wx.loadFontFace({
      global: true,
      family: "Long Cang",
      source: 'url("' + LONG_CANG_FONT_URL + '")',
      fail: function () {
        /* 降级 Kaiti SC — paper-ink.wxss font-family 已兜底,无需处理 */
      },
    });
  },

  _load() {
    var that = this;
    var opt = { silent: true };
    var settle = function (p) {
      return Promise.resolve(p).then(
        function (r) {
          return r;
        },
        function () {
          return null; // 单源失败不拖垮整页(降级)
        }
      );
    };
    return Promise.all([
      settle(api.getHomeDashboard(opt)),
      settle(api.getLearningReport(100, opt)),
      settle(api.getLubanLessons(opt)),
    ]).then(function (res) {
      var homeDashboard = api.unwrapResponse(res[0]) || {};
      var report = api.unwrapResponse(res[1]) || {};
      var lessons = api.unwrapResponse(res[2]) || {};
      var vm = buildLearnViewModel({ homeDashboard: homeDashboard, report: report, lessons: lessons });
      that.setData({ vm: vm, loading: false });
    });
  },

  toggleWhy() {
    this.setData({ whyOpen: !this.data.whyOpen });
  },

  // 下一站卡「播放」/ 课程架海报 → 进 spike 站点页(复用两幕 web-view 播放器)
  openStation(event) {
    var ds = (event && event.currentTarget && event.currentTarget.dataset) || {};
    var packId = ds.packId || (this.data.vm && this.data.vm.nextStation && this.data.vm.nextStation.pack_id);
    var green = ds.green;
    if (!packId) return;
    if (green === false) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "这一站即将开通", icon: "none" });
      return;
    }
    this._navTo("/packageDeeptutor/pages/luban/station/station?pack_id=" + encodeURIComponent(String(packId)));
  },

  // 完整路线 → 站点列表(纸墨朱竹路线图)
  openStations() {
    this._navTo("/packageDeeptutor/pages/luban/stations/stations");
  },

  // 复习到期条 → 复习(错题本);今日任务 → 现有 practice/chat(练三档真答题流后续片)
  goReview() {
    this._navTo("/packageDeeptutor/pages/mistake-book/mistake-book");
  },
  goPractice() {
    this._navTo("/packageDeeptutor/pages/chat/chat");
  },

  // 底部 tab 路由(设计 5tab → 现有页;归位后续片)
  tabReview() {
    this._navTo("/packageDeeptutor/pages/mistake-book/mistake-book");
  },
  tabAsk() {
    this._navTo("/packageDeeptutor/pages/chat/chat");
  },
  tabReport() {
    this._navTo("/packageDeeptutor/pages/report/report");
  },
  tabProfile() {
    this._navTo("/packageDeeptutor/pages/profile/profile");
  },

  _navTo(url) {
    if (typeof wx !== "undefined" && wx.navigateTo) wx.navigateTo({ url: url });
  },
});
