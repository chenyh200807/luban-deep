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

// 学情快照 SWR 加速层(可选依赖):快照是「可丢弃的 UI 加速层」,canonical truth
// 仍在服务端 read model。try/catch + 能力检查:存量学习页测试 harness 的 require
// 白名单不含这两个模块(未知 require 直接 throw / 返回 {}),加速层缺席时必须
// 静默降级为原无缓存路径,不得让加速层变成致命依赖。线上运行时两模块恒存在。
var reportCache = null;
var reportSnapshot = null;
try { reportCache = require("../../utils/report-cache"); } catch (_) { reportCache = null; }
try { reportSnapshot = require("../../utils/report-snapshot"); } catch (_) { reportSnapshot = null; }
var snapshotLayerReady = Boolean(
  reportCache &&
    typeof reportCache.read === "function" &&
    typeof reportCache.writeIfFresher === "function" &&
    reportSnapshot &&
    typeof reportSnapshot.buildUnifiedReportSnapshot === "function",
);

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
    stationOpen: true, // 一体化站点卡折叠态(定稿 10a 头部行折叠箭头);默认展开
    stationWhyOpen: false, // 「为什么先走这一站」折叠态
    supplyError: "",
    firstRunState: "new", // new | resume | syncing | blocked | hidden
    firstRunProgress: 0,
  },

  onLoad(query) {
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48, isDark: helpers.isDarkOr("light") });
    this._loadLongCangFont();
    if (!this._requireAuth()) return;
    this._load();
  },

  onShow() {
    surfaceTelemetry.trackModuleView(this, { module: "learning", section: "home" });
    // 主题单一权威:tab 常驻页在 onShow 重读(外观切换后返回本 tab 需生效)
    this.setData({ isDark: helpers.isDarkOr("light") });
    // 五 tab 壳:学习 index=0;壳跟页面主题
    helpers.syncTabBar(this, 0, {
      isDark: this.data.isDark,
      hidden: !flags.shouldShowWorkspaceShell(),
    });
    if (!this._requireAuth()) return;
    const firstRunSnapshot = this._syncFirstRunState();
    this._retryPendingFirstRun(firstRunSnapshot);
    // 首个 onShow 紧跟 onLoad(_load 已由 onLoad 发起),不重复触发;
    // 后续 onShow = 从站点/练习返回(刚发生学习动作),重新加载 canonical 投影
    // (统一策略=缓存秒渲染+始终静默刷新,无 fresh 门可绕;
    // 并发安全由 _load 的单调 request epoch 保证)。
    if (!this._shownOnce) {
      this._shownOnce = true;
    } else {
      this._load();
    }
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
    // 本地 DONE 缓存丢失（清缓存/换设备）→ 老用户被首跑门错误挡住。canonical
    // 完成态真值在服务端 Learner State，回读一次投影并 rehydrate 本地缓存。
    // 每个页面生命周期只查一次（本地已有 DONE 时 entry 层也会短路不打接口）。
    if (snapshot.state === "new" && !this._firstRunServerChecked) {
      this._firstRunServerChecked = true;
      this._rehydrateFirstRunFromServer(userId);
    }
    return snapshot;
  },

  // 服务端完成态回读：只把门从 new → hidden（fail-safe），绝不回退一个本地
  // 已激活的门（resume/syncing 期间不触发本路径）。
  _rehydrateFirstRunFromServer(userId) {
    const that = this;
    return firstRunEntry
      .refreshFromServer(userId, api)
      .then(function (snapshot) {
        if (snapshot && snapshot.state === "hidden") {
          that.setData({ firstRunState: "hidden", firstRunProgress: 0 });
          if (!that.data.loading) that._load();
        }
        return snapshot;
      })
      .catch(function () {
        return null;
      });
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
        // 首跑完成刚同步到服务端(学习动作落账),重新拉取 canonical 投影
        // (_load 本就始终静默刷新)。
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
    // 用户显式下拉 = 真刷新;_load 本就始终静默刷新,无 fresh 门可吞。
    this._load().then(function () {
      if (typeof wx !== "undefined" && wx.stopPullDownRefresh) wx.stopPullDownRefresh();
    });
  },

  retrySupply() {
    if (!this._requireAuth()) return;
    this.setData({ loading: true, supplyError: "" });
    // 错误重试 = 用户显式要求重取;_load 本就始终静默刷新。
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
    // 写序守卫(对抗 review #8/#9):记录发起时刻与发起者身份;网络成功写缓存前
    // 由 cache 权威层按 fetchStartedAt 裁决写序(孤儿响应=页面已销毁的在途请求,
    // 其发起时刻早于现存快照写入时刻,在 writeIfFresher 内拒写)。
    var fetchStartedAt = Date.now();
    var startedUserId = String((auth.getUserId && auth.getUserId()) || "").trim();
    // 红队 A4:单调 request epoch——onShow 静默刷新与下拉刷新可并发,
    // 只有最新一代请求可 setData,乱序到达的旧响应(旧供给 true)一律丢弃;
    // 刷新 in-flight 期间轻练 CTA 禁点(goLightPractice 检查 _refreshing)。
    var seq = (this._loadSeq || 0) + 1;
    this._loadSeq = seq;
    this._refreshing = true;
    // ── 快照秒渲染:tab redirectTo 冷启动的 3-5s 重 read model 等待期,先用
    // 30min 内快照秒渲染整页(诚实旧投影,非发明数据;组装仍走唯一 builder)。
    // 统一策略=缓存秒渲染+始终静默刷新——曾有的 fresh-skip 门被对抗 review
    // 证伪删除(它会把陈旧/降级/半残快照钉成终态),hydrate 后无条件继续刷新。
    var cached = snapshotLayerReady
      ? reportCache.read(startedUserId, reportCache.SNAPSHOT_MAX_AGE_MS)
      : null;
    if (cached && !this.data.vm) {
      var cachedVm = buildLearnViewModel({
        // builder 把空对象 homeDashboard/lessons 归一化为 null,消费侧补 {}。
        homeDashboard: cached.homeDashboard || {},
        report: cached.report || {},
        lessons: cached.lessons || {},
      });
      // 与下方 lessons 快通道同一门:空态投影不上屏(宁等真数据,不闪空态)。
      if (cachedVm.hasSupply) this.setData({ vm: cachedVm, loading: false, supplyError: "" });
    }
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
        if (seq !== that._loadSeq) return; // 乱序旧响应,丢弃
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
    ]).then(function (res) {
      if (seq !== that._loadSeq) return null; // 乱序旧响应,不得覆盖最新投影
      that._refreshing = false;
      if (!auth.isLoggedIn()) {
        that._requireAuth();
        return null;
      }
      var homeDashboard = api.unwrapResponse(res[0]) || {};
      var report = api.unwrapResponse(res[1]) || {};
      var lessons = api.unwrapResponse(res[2]) || {};
      var vm = buildLearnViewModel({
        homeDashboard: homeDashboard,
        report: report,
        lessons: lessons,
      });
      that.setData({ vm: vm, loading: false, supplyError: "" });
      // 第二合法写者(与学情页共用唯一组装权威 buildUnifiedReportSnapshot):
      // report 无效(如 unwrap 出的空对象)时 builder 返回 null 即不写,防污染。
      // 写侧守卫(review #8/#9):re-check 当前登录者仍是发起者(用户中途切换
      // 一律拒写),再经 writeIfFresher 按 fetchStartedAt 在 cache 权威层裁决
      // 写序(孤儿响应拒写)。
      if (
        snapshotLayerReady &&
        auth.isLoggedIn() &&
        String((auth.getUserId && auth.getUserId()) || "").trim() === startedUserId
      ) {
        var snap = reportSnapshot.buildUnifiedReportSnapshot({
          report: report,
          homeDashboard: homeDashboard,
          lessons: lessons,
        });
        if (snap) reportCache.writeIfFresher(startedUserId, snap, fetchStartedAt);
      }
      return vm;
    }).catch(function (err) {
      if (seq !== that._loadSeq) return null;
      that._refreshing = false;
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

  // 一体化站点卡折叠(定稿 10a 头部行折叠箭头):纯呈现层,不触发任何加载/写入
  toggleStation() {
    this.setData({ stationOpen: !this.data.stationOpen });
  },

  // 「为什么先走这一站」折叠:展示 nextStation.reason(群体/证据理由,不算分)
  toggleStationWhy() {
    this.setData({ stationWhyOpen: !this.data.stationWhyOpen });
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

  // 今日唯一任务只按 view-model 的 action_kind 转发：到期验证/课后练共用
  // retest，推荐学习进站点；页面不重算优先级、不解释掌握状态。
  // 二轮红队 A4:主任务按钮与复习卡共用本 handler,刷新 in-flight 期间
  // 旧 VM 的 pack/probe 身份可能已过期,与 goLightPractice 同一守卫禁点。
  goTodayTask() {
    if (this._refreshing) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "正在刷新，请稍候", icon: "none" });
      return;
    }
    // 任务卡渲染源 = taskCard(todayTask || browseTask 单一入口);browse 兜底卡
    // 与真今日任务同构,主按钮路由复用同一 handler(禁第二套路由)。
    var vmData = this.data.vm || {};
    var task = vmData.taskCard || vmData.todayTask || {};
    var packId = encodeURIComponent(String(task.pack_id || ""));
    if (task.action_kind === "lesson" && packId) {
      this._navTo(route.lubanStation(String(task.pack_id || "")));
      return;
    }
    if (task.action_kind === "retest" && task.practice_kind === "retest" && packId) {
      this._navTo(
        "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
          packId +
          "&mode=" +
          (task.mode === "review" ? "review" : "forward") +
          "&training_intent_id=" +
          encodeURIComponent(String(task.training_intent_id || "")) +
          "&probe_id=" +
          encodeURIComponent(String(task.probe_id || "")),
      );
      return;
    }
  },

  // 一体化站点卡舞台播放/进站学习(第10轮定稿:学习动作走站点卡舞台点击)。
  // 目标站 = vm.nextStation(next_step 呈现仲裁的推荐学习站),不重算推荐;
  // card_hosted===false 诚实降级 toast(禁 dead click 假可播)。
  goLesson() {
    if (this._refreshing) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "正在刷新，请稍候", icon: "none" });
      return;
    }
    var station = (this.data.vm && this.data.vm.nextStation) || {};
    var packId = String(station.pack_id || "");
    if (!packId) return;
    if (station.card_hosted === false) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "这一站微课即将开通", icon: "none" });
      return;
    }
    this._navTo(route.lubanStation(packId));
  },

  // 轻练旁按钮:供给真值由 view-model 单点裁决(light_practice_available,
  // 来自 lessons manifest 的 light_practice_available 旗标);页面不重判供给。
  // 未接通时给诚实空态提示——禁 dead click 假装可用。
  // 红队 A2/A4 收口:轻练只复用当前任务的 fact 语境,不是第二处方——
  // review_due 下禁 probe-less forward 旁路(绕开到期验证会重开 fresh cycle);
  // 供给刷新 in-flight 期间禁点(旧 VM 的供给旗标可能已被撤回)。
  goLightPractice() {
    if (this._refreshing) {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "正在刷新，请稍候", icon: "none" });
      return;
    }
    var vmData = this.data.vm || {};
    var task = vmData.taskCard || vmData.todayTask || {};
    if (task.task_state === "review_due") {
      if (typeof wx !== "undefined" && wx.showToast)
        wx.showToast({ title: "先完成今天的到期验证", icon: "none" });
      return;
    }
    if (task.light_practice_available === true && task.pack_id) {
      this._navTo(
        "/packageDeeptutor/pages/luban/retest/retest?pack_id=" +
          encodeURIComponent(String(task.pack_id)) +
          "&mode=forward&training_intent_id=" +
          encodeURIComponent(
            String(task.task_state === "practice_active" ? task.training_intent_id || "" : ""),
          ) +
          "&probe_id=",
      );
      return;
    }
    if (typeof wx !== "undefined" && wx.showToast)
      wx.showToast({ title: "快练准备中", icon: "none" });
  },

  _navTo(url) {
    if (typeof wx !== "undefined" && wx.navigateTo) wx.navigateTo({ url: url });
  },
});
