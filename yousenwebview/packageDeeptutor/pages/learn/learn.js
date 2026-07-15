// 学习 tab · 纸墨朱竹宣纸驾驶舱(五模块第 10 轮定稿 10a/10b)
// 只读投影:并发拉 next_step(homepage/dashboard)+ pack_lifecycle/stats(learning-report)
// + 绿灯站(luban/lessons)→ learn-view-model 组装 → setData。
// 零学习证据写入(学习证据归 lesson-progress[讲懂幕] / 判分链路)。
// 全程降级:任一 read model 字段缺(test2 后端未部署常态)不崩,走空态。
const api = require("../../utils/api");
const auth = require("../../utils/auth");
const firstRunEntry = require("../../utils/first-run-entry");
const helpers = require("../../utils/helpers");
const route = require("../../utils/route");
const runtime = require("../../utils/runtime");
const flags = require("../../utils/flags");
const surfaceTelemetry = require("../../utils/surface-telemetry");
const { buildLearnViewModel } = require("../../utils/learn-view-model");

// H2:Long Cang 只许 CDN 子集化,禁内嵌。子集托管后填此常量;
// 空/失败 → 降级 'Kaiti SC', serif(paper-ink.wxss font-family 已兜底)。
const LONG_CANG_FONT_URL = "";

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false,
    loading: true,
    vm: null, // learn-view-model 输出
    whyOpen: false,
    supplyError: "",
    firstRunState: "new", // new | resume | syncing | blocked | hidden
    firstRunProgress: 0,
  },

  onLoad(query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48, isDark: false /* 第10版主色=宣纸亮,默认亮色;夜宣纸暗版 wxss 仍在 */ });
    this._loadLongCangFont();
    if (!this._requireAuth()) return;
    this._load();
  },

  onShow() {
    surfaceTelemetry.trackModuleView(this, { module: "learning", section: "home" });
    // 五 tab 壳:学习 index=0;本页第 10 版定稿=宣纸亮,壳跟页面主题
    helpers.syncTabBar(this, 0, {
      isDark: this.data.isDark,
      hidden: !flags.shouldShowWorkspaceShell(),
    });
    if (!this._requireAuth()) return;
    const firstRunSnapshot = this._syncFirstRunState();
    this._retryPendingFirstRun(firstRunSnapshot);
    // 从站点/复习返回时刷新 canonical 投影。
    if (!this.data.loading) this._load();
  },

  onHide() {
    surfaceTelemetry.trackModuleExit(this);
  },

  onUnload() {
    surfaceTelemetry.trackModuleExit(this);
  },

  _syncFirstRunState() {
    const userId = String((auth && auth.getUserId && auth.getUserId()) || "").trim();
    if (!userId) {
      this.setData({ firstRunState: "hidden", firstRunProgress: 0 });
      return { state: "hidden", checkpoint: null, pending: null };
    }
    const snapshot = firstRunEntry.getState(userId);
    const checkpoint = snapshot.checkpoint || {};
    const progress = Math.max(0, Math.min(Number(checkpoint.qIndex || 0) + 1, 4));
    this.setData({ firstRunState: snapshot.state, firstRunProgress: progress });
    return snapshot;
  },

  _retryPendingFirstRun(snapshot) {
    const current = snapshot || this._syncFirstRunState();
    const pending = current && current.pending;
    const userId = String((auth && auth.getUserId && auth.getUserId()) || "").trim();
    if (!pending || !userId || this._firstRunSyncing) return Promise.resolve(null);
    this._firstRunSyncing = true;
    this.setData({ firstRunState: "syncing" });
    const that = this;
    // 陈旧pending的script_version自愈: 签发翻牌会改版本号(题集与内容sha未变),
    // 老payload按当前常量重放, 避免永久version_conflict
    const scriptData = require("../first-run/script-data");
    if (scriptData && scriptData.SCRIPT_VERSION && pending.script_version !== scriptData.SCRIPT_VERSION) {
      pending.script_version = scriptData.SCRIPT_VERSION;
    }
    return api
      .completeFirstRun(pending, { silent: true, suppressAuthRedirect: true })
      .then(function (result) {
        firstRunEntry.clearPendingSync(userId);
        if (typeof firstRunEntry.clearCheckpoint === "function") {
          firstRunEntry.clearCheckpoint(userId);
        }
        firstRunEntry.markDone(userId, pending);
        that.setData({ firstRunState: "hidden", firstRunProgress: 4 });
        that._load();
        return result;
      })
      .catch(function (error) {
        if (!auth.isLoggedIn()) {
          that._requireAuth();
          return null;
        }
        const code = api.errorCodeOf(error);
        that.setData({
          firstRunState:
            code === "first_run_content_not_signed" || code === "first_run_version_conflict"
              ? "blocked"
              : "syncing",
        });
        return null;
      })
      .then(function (result) {
        that._firstRunSyncing = false;
        return result;
      });
  },

  openFirstRun() {
    if (this.data.firstRunState === "syncing") return;
    if (this.data.firstRunState === "blocked") {
      this._retryPendingFirstRun();
      return;
    }
    this._navTo(route.resolve("pages/first-run/first-run"));
  },

  onPullDownRefresh() {
    var that = this;
    this._load().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) wx.stopPullDownRefresh();
    });
  },

  retrySupply() {
    if (!this._requireAuth()) return;
    this.setData({ loading: true, supplyError: "" });
    return this._load();
  },

  _requireAuth() {
    if (auth.isLoggedIn()) {
      this._authRedirectPending = false;
      return true;
    }
    if (!this._authRedirectPending) {
      this._authRedirectPending = true;
      runtime.redirectToLogin(route.learn());
    }
    return false;
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
    if (!this._requireAuth()) return Promise.resolve(null);
    // 页面拥有 returnTo 语义；API 只清理过期 token 并返回错误，不能抢先跳默认登录。
    var opt = { silent: true, suppressAuthRedirect: true };
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
    // 教学供给是本页唯一内容 authority：dashboard/report 可以独立降级，
    // lessons 失败不能伪装成“微课未上线”。
    var lessonsPromise = Promise.resolve(api.getLubanLessons(opt));
    // 首屏快通道:绿灯站列表是静态 manifest 投影(live 实测 ~0.15s),
    // dashboard/learning-report 是重 read model(live 实测 3-5s)。
    // 冷启动先用 lessons 画出舞台+课程架(view-model 对缺 dashboard/report
    // 本就降级),整页数据到齐后再覆盖——不发明数据,只是分两拍投影。
    lessonsPromise.then(
      function (lessonsRes) {
        if (that.data.vm) return; // 已有整页数据(onShow 静默刷新),不做部分回退
        var lessons = api.unwrapResponse(lessonsRes) || {};
        var fast = buildLearnViewModel({ homeDashboard: {}, report: {}, lessons: lessons });
        if (fast.hasSupply) that.setData({ vm: fast, loading: false, supplyError: "" });
      },
      function () {
        // 最终错误由下方 Promise.all 的单一终态处理，避免第二套错误文案。
      },
    );
    return Promise.all([
      settle(api.getHomeDashboard(opt)),
      settle(api.getLearningReport(100, opt)),
      lessonsPromise,
      // 看穿库总览:头牌轻练 practice_kind 供给真值之一(失败=空集保守降级)
      settle(api.getLubanSeethroughLibrary(opt)),
    ]).then(function (res) {
      if (!auth.isLoggedIn()) {
        that._requireAuth();
        return null;
      }
      var homeDashboard = api.unwrapResponse(res[0]) || {};
      var report = api.unwrapResponse(res[1]) || {};
      var lessons = api.unwrapResponse(res[2]) || {};
      var seethroughLibrary = api.unwrapResponse(res[3]) || {};
      var vm = buildLearnViewModel({
        homeDashboard: homeDashboard,
        report: report,
        lessons: lessons,
        seethroughLibrary: seethroughLibrary,
      });
      that.setData({ vm: vm, loading: false, supplyError: "" });
      return vm;
    }).catch(function (err) {
      if (!auth.isLoggedIn()) {
        that._requireAuth();
        return null;
      }
      var fallbackVm = that.data.vm || buildLearnViewModel({});
      that.setData({
        vm: fallbackVm,
        loading: false,
        supplyError: api.describeRequestError(
          err,
          "教学资源加载失败，请检查登录或网络后重试",
        ),
      });
      return null;
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
    var cardHosted = ds.cardHosted;
    if (!packId) return;
    if (green === false) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "这一站即将开通", icon: "none" });
      return;
    }
    if (cardHosted === false) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "这一站微课即将开通", icon: "none" });
      return;
    }
    this._navTo("/packageDeeptutor/pages/luban/station/station?pack_id=" + encodeURIComponent(String(packId)));
  },

  // 完整路线 → 74 集 C 版强弱分句路线
  openStations() {
    this._navTo(route.lubanTeachingPoints());
  },

  // 复习到期条 → 复习页(10c 回炉屏, 归位);今日任务 → 现有 practice/chat
  goReview() {
    this._navTo(route.lubanReview());
  },
  // 今日主任务「开始 2 分钟轻练」→ 按供给真值路由(practice_kind 由 vm 单一裁决,
  // 页面零判定):有签发看穿包 → 看穿 5 天;有 signed 变体池 → retest 正向轻练;
  // 无供给 → 主按钮不渲染(WXML cta 空即隐藏),这里只兜底 noop。
  goPractice() {
    var task = (this.data.vm && this.data.vm.todayTask) || {};
    var packId = encodeURIComponent(String(task.pack_id || ""));
    if (task.practice_kind === "seethrough" && packId) {
      this._navTo("/packageDeeptutor/pages/luban/seethrough/seethrough?pack_id=" + packId);
      return;
    }
    if (task.practice_kind === "retest" && packId) {
      var reviewMode = !!task.probe_id;
      this._navTo(
        "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
          packId +
          "&mode=" +
          (reviewMode ? "review" : "forward") +
          "&training_intent_id=" +
          encodeURIComponent(String(task.training_intent_id || "")) +
          "&probe_id=" +
          encodeURIComponent(String(task.probe_id || "")),
      );
      return;
    }
  },

  // 今日任务副 CTA「换轻练」→ 换成更广/更轻的综合摸底(与主任务不同动作):
  // assessment 综合模式(mode=diagnostic),同样复用既有 MCQ 流,不判分。
  goSwitchPractice() {
    this._navTo(route.assessment({ mode: "diagnostic", source: "today_task_switch" }));
  },

  // F16 防水「5天留存闭环」雏形入口(spike 审阅):进原生 5 天体验,内容全部
  // 投影自已签发看穿包,前端不新造。pack 暂定 F16(雏形单母题)。
  goSeethrough() {
    this._navTo("/packageDeeptutor/pages/luban/seethrough/seethrough?pack_id=F16");
  },

  _navTo(url) {
    if (typeof wx !== "undefined" && wx.navigateTo) wx.navigateTo({ url: url });
  },
});
