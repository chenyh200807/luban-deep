// 学习 tab · 纸墨朱竹宣纸驾驶舱(五模块第 10 轮定稿 10a/10b)
// 只读投影:并发拉 next_step(homepage/dashboard)+ pack_lifecycle/stats(learning-report)
// + 绿灯站(luban/lessons)→ learn-view-model 组装 → setData。
// 零学习证据写入(学习证据归 lesson-progress[讲懂幕] / 判分链路)。
// 全程降级:任一 read model 字段缺(test2 后端未部署常态)不崩,走空态。
const api = require("../../utils/api");
const helpers = require("../../utils/helpers");
const runtime = require("../../utils/runtime");
const route = require("../../utils/route");
const flags = require("../../utils/flags");
const { buildLearnViewModel } = require("../../utils/learn-view-model");

// H2:Long Cang 只许 CDN 子集化,禁内嵌。子集托管后填此常量;
// 空/失败 → 降级 'Kaiti SC', serif(paper-ink.wxss font-family 已兜底)。
const LONG_CANG_FONT_URL = "";

// 设计预览数据(?preview=1):镜像第 10 版 10a 的代表性数据,专供视觉审核
// (后端未部署时看完整设计:三态海报/舞台/72% 掌握环/今日任务/复习条)。
// 仅审核用,非 live 数据;真数据走 _load 的后端 read model。
const PREVIEW_VM = {
  litCount: 12,
  packUniverse: 40,
  nextStation: {
    pack_id: "S07",
    title: "安全事故等级判定与上报",
    reason: "你最近 3 次都漏写「是否影响关键线路」,这类题通常丢 2–4 分。",
    mode: "learn_next",
    green: true,
    card_sha: "preview",
  },
  posters: [
    { pack_id: "S07", title: "安全事故", slot: "S07", green: true, state: "red", recommended: true, locked: false },
    { pack_id: "S02", title: "工期索赔", slot: "S02", green: true, state: "ink", recommended: false, locked: false },
    { pack_id: "A01", title: "质量验收", slot: "A01", green: true, state: "ink", recommended: false, locked: false },
    { pack_id: "B08", title: "基坑支护", slot: "B08", green: false, state: "paper", recommended: false, locked: true },
  ],
  dueCount: 3,
  todayTask: {
    title: "工期索赔 · 半写训练 1 题",
    reason: "你最近 3 次都漏写「是否影响关键线路」,这类题通常丢 2–4 分。",
    cta: "开始半写训练",
    concept: "工期索赔",
    prompt: "针对『工期索赔』给我一道案例题做半写训练。我先真实作答,你再按采分点逐条批改并定位我的盲点,不要提前给答案和解析。",
  },
  stats: { recent_practice: 8, pending_errors: 3, mastery_trend: 72 },
  hasSupply: true,
};

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false,
    loading: true,
    vm: null, // learn-view-model 输出
    whyOpen: false,
  },

  onLoad(query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48, isDark: false /* 第10版主色=宣纸亮,默认亮色;夜宣纸暗版 wxss 仍在 */ });
    this._loadLongCangFont();
    // 设计预览模式:?preview=1 用镜像第 10 版的数据渲染完整设计(审核用,不打后端)
    if (query && String(query.preview) === "1") {
      this.setData({ vm: PREVIEW_VM, loading: false, _preview: true });
      return;
    }
    this._load();
  },

  onShow() {
    // 五 tab 壳:学习 index=0;本页第 10 版定稿=宣纸亮,壳跟页面主题
    helpers.syncTabBar(this, 0, {
      isDark: this.data.isDark,
      hidden: !flags.shouldShowWorkspaceShell(),
    });
    // 从站点/复习返回时刷新点亮态(预览模式不打后端,保持镜像数据)
    if (!this.data.loading && !this.data._preview) this._load();
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
    var lessonsPromise = settle(api.getLubanLessons(opt));
    // 首屏快通道:绿灯站列表是静态 manifest 投影(live 实测 ~0.15s),
    // dashboard/learning-report 是重 read model(live 实测 3-5s)。
    // 冷启动先用 lessons 画出舞台+课程架(view-model 对缺 dashboard/report
    // 本就降级),整页数据到齐后再覆盖——不发明数据,只是分两拍投影。
    lessonsPromise.then(function (lessonsRes) {
      if (that.data.vm) return; // 已有整页数据(onShow 静默刷新),不做部分回退
      var lessons = api.unwrapResponse(lessonsRes) || {};
      var fast = buildLearnViewModel({ homeDashboard: {}, report: {}, lessons: lessons });
      if (fast.hasSupply) that.setData({ vm: fast, loading: false });
    });
    return Promise.all([
      settle(api.getHomeDashboard(opt)),
      settle(api.getLearningReport(100, opt)),
      lessonsPromise,
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

  // 复习到期条 → 复习页(10c 回炉屏, 归位);今日任务 → 现有 practice/chat
  goReview() {
    this._navTo(route.lubanReview());
  },
  // 今日任务入口(由 task_type 分流,不新建第二答题页):
  // - light_practice:2 分钟正向轻练 → 复用 retest 页 forward 模式(带 pack_id);
  //   本地判分、证据非 promoting、完成发 station_completed 交接次日复习。
  // - half_write / 摸底:直达半写训练,复用唯一答题流
  //   (runtime.setPendingChatIntent → chat/TutorBot 案例题+采分点批改)。
  // 前端只投递作答意图或跳转,不判分、不造第二套答题入口。
  goPractice() {
    var task = this.data.vm && this.data.vm.todayTask;
    if (task && task.task_type === "light_practice" && task.pack_id) {
      this._navTo(
        "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
          encodeURIComponent(String(task.pack_id)) +
          "&mode=forward",
      );
      return;
    }
    var prompt = task && task.prompt;
    if (prompt && typeof wx !== "undefined" && wx.reLaunch) {
      runtime.setPendingChatIntent(prompt, "AUTO");
      wx.reLaunch({ url: route.chat() });
      return;
    }
    this._navTo("/packageDeeptutor/pages/practice/practice");
  },

  _navTo(url) {
    if (typeof wx !== "undefined" && wx.navigateTo) wx.navigateTo({ url: url });
  },
});
