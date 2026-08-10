// 计划页(跑道视图) —— AI 学习计划体系 P0 竖切 / 首页跑道反转 §2。
// 只读投影,前端不算分不排序不造数(单一权威清单见 plan-view-model.js 头注):
// - 7 天任务 = /api/v1/luban/exam-prep-plan(exam_prep_plan_projection 薄透传);
// - 任务→动作 = buildCanonicalLearningTask 唯一翻译器(经 plan-view-model);
// - 收敛条 = 后端透传的过线体检报告值 + 距考天数(无报告 → 体检引导卡);
// - defer = 唯一 learner-signal 写器(复习带 probe_id 落 declined 机制),
//   成功后重拉投影(重排是服务端的事,本页只刷新)。
var api = require("../../../utils/api");
var auth = require("../../../utils/auth");
var helpers = require("../../../utils/helpers");
var route = require("../../../utils/route");
var runtime = require("../../../utils/runtime");
var telemetry = require("../../../utils/surface-telemetry");
var planViewModel = require("../../../utils/plan-view-model");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 96,
    isDark: false, // 主题单一权威:宣纸亮默认(与 review/stations 同口径)
    loading: true,
    errorText: "",
    vm: null, // plan-view-model 输出;vm.enabled === false → 未开通占位
  },

  onLoad: function () {
    this._hasShown = false;
    this._deferring = false;
    var info =
      typeof wx !== "undefined" && wx.getSystemInfoSync
        ? wx.getSystemInfoSync()
        : {};
    var sbh = info.statusBarHeight || 0;
    this.setData({ statusBarHeight: sbh, navHeight: sbh + 48, isDark: helpers.isDarkOr("light") });
    if (!auth.isLoggedIn()) {
      runtime.redirectToLogin(route.lubanPlan());
      return;
    }
    telemetry.trackModuleView(this, { module: "learning", section: "plan" });
    this._loadAll();
  },

  onShow: function () {
    // 从站点/复测返回 = 刚发生学习动作,重拉 canonical 投影(服务端重排)。
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

  goLearn: function () {
    if (typeof wx === "undefined" || !wx.redirectTo) return;
    wx.redirectTo({
      url: route.learn(),
      fail: function () {
        if (wx.reLaunch) wx.reLaunch({ url: route.learn() });
      },
    });
  },

  // 收敛条无报告 → 过线体检引导(获客诊断入口,永远免费)。
  goAssessment: function () {
    this._navTo(route.assessment());
  },

  // 任务点击:只转发 view-model 派发的 actionUrl(翻译器唯一权威;
  // 无 actionUrl = display-only,禁 dead click 假路由)。
  openTask: function (event) {
    if (this._deferring) return;
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var task = this._findTask(dataset.dayOffset, dataset.taskKey);
    if (!task || !task.actionUrl) return;
    this._navTo(task.actionUrl);
  },

  // defer 手柄(仅复习/learn 任务,view-model canDefer 单点裁决):
  // 唯一写器 learner-signal;复习必带 probe_id(落 declined 机制)。
  // 成功后重拉投影——重排与替补是服务端投影的事,前端零自算;后果文案位诚实提示。
  deferTask: function (event) {
    var that = this;
    if (this._deferring) return;
    var dataset =
      (event && event.currentTarget && event.currentTarget.dataset) || {};
    var task = this._findTask(dataset.dayOffset, dataset.taskKey);
    if (!task || !task.canDefer || !task.packId) return;
    var confirmContent =
      task.family === "review_probe"
        ? "推迟到期复验会提高遗忘回退的风险；明天它会重新排进计划。"
        : "今天先不安排它，计划会重新编排后续内容。";
    var doDefer = function () {
      that._deferring = true;
      api
        .postPlanDefer(task.packId, task.deferProbeId)
        .then(function () {
          if (typeof wx !== "undefined" && wx.showToast)
            wx.showToast({ title: "已推迟 · 计划已重排", icon: "none" });
          return that._loadAll();
        })
        .catch(function () {
          if (typeof wx !== "undefined" && wx.showToast)
            wx.showToast({ title: "推迟失败，请稍后重试", icon: "none" });
        })
        .then(function () {
          that._deferring = false;
        });
    };
    if (typeof wx !== "undefined" && wx.showModal) {
      wx.showModal({
        title: "今天不练这个？",
        content: confirmContent,
        confirmText: "推迟",
        cancelText: "再想想",
        success: function (res) {
          if (res && res.confirm) doDefer();
        },
      });
    } else {
      doDefer();
    }
  },

  _findTask: function (dayOffset, taskKey) {
    var vm = this.data.vm;
    var days = (vm && vm.days) || [];
    for (var i = 0; i < days.length; i++) {
      if (String(days[i].dayOffset) !== String(dayOffset)) continue;
      var tasks = days[i].tasks || [];
      for (var j = 0; j < tasks.length; j++) {
        if (tasks[j].key === taskKey) return tasks[j];
      }
    }
    return null;
  },

  _loadAll: function () {
    var that = this;
    var seq = (this._loadSeq = (this._loadSeq || 0) + 1);
    this.setData({ loading: !this.data.vm, errorText: "" });
    var opt = { silent: true, suppressAuthRedirect: true };
    var settle = function (p) {
      return Promise.resolve(p).then(
        function (r) {
          return { ok: true, value: r };
        },
        function (error) {
          return { ok: false, error: error };
        },
      );
    };
    return Promise.all([
      settle(api.getLubanExamPrepPlan(opt)),
      settle(api.getLubanLessons(opt)),
      settle(api.getLearningReport(100, opt)),
    ]).then(function (res) {
      if (seq !== that._loadSeq) return null; // 乱序旧响应,不覆盖最新投影
      if (!auth.isLoggedIn()) {
        runtime.redirectToLogin(route.lubanPlan());
        return null;
      }
      var planResult = res[0] || { ok: false };
      if (!planResult.ok) {
        // 计划投影是本页唯一内容 authority:拿不到就是错误终态,
        // 不能用 lessons/report 拼一个假计划。
        that.setData({
          loading: false,
          errorText: "计划暂时读不出来，请下拉重试",
        });
        return null;
      }
      var planResp = api.unwrapResponse(planResult.value) || {};
      // lessons/report 可独立降级:只影响翻译器的供给判定(fail-closed →
      // 任务 display-only),不影响计划本身的展示。
      var lessons = planResult.ok && res[1] && res[1].ok ? api.unwrapResponse(res[1].value) || {} : {};
      var report = res[2] && res[2].ok ? api.unwrapResponse(res[2].value) || {} : {};
      var vm = planViewModel.buildPlanViewModel({
        planResp: planResp,
        lessons: lessons,
        report: report,
      });
      that.setData({ vm: vm, loading: false, errorText: "" });
      return null;
    });
  },

  _navTo: function (url) {
    if (typeof wx !== "undefined" && wx.navigateTo) wx.navigateTo({ url: url });
  },
});
