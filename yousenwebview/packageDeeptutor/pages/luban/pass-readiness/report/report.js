// 过线体检(S5)· 报告页(屏 3-9, section 驱动)
// section: result(屏3 结果首屏) | evidence(屏4 证据) | plan(屏5 三优先预览)
//        | receipt(屏7 复测收据) | save(屏8 保存) | saved(保存成功态, 亦是
//          新用户完成后的参数化落点当前值) | member(屏9 会员 handoff)
// 屏 6(微课)与屏 7 复测作答跳既有 station / retest 页(既有路由), 本页不复刻。
// 数据权威: 报告 = submit 响应快照(owner storage) 或 GET /assessment/{id}/report;
// 是否完成过诊断 = /assessment/profile diagnostic_sources.pass_readiness(禁前端自判)。
var api = require("../../../../utils/api");
var auth = require("../../../../utils/auth");
var helpers = require("../../../../utils/helpers");
var route = require("../../../../utils/route");
var surfaceTelemetry = require("../../../../utils/surface-telemetry");
var passVm = require("../../../../utils/pass-readiness-view-model");
var reportVm = require("../../../../utils/pass-readiness-report-view-model");

var SECTIONS = {
  result: true,
  evidence: true,
  plan: true,
  receipt: true,
  save: true,
  saved: true,
  member: true,
};

function trackBehavior(eventName, payload) {
  if (surfaceTelemetry && typeof surfaceTelemetry.trackProductBehavior === "function") {
    surfaceTelemetry.trackProductBehavior(eventName, payload);
  }
}

function _obj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}

Page({
  data: {
    isDark: false,
    statusBarHeight: 44,
    navHeight: 96,
    stage: "loading", // loading | ready | error
    errorText: "",
    section: "result",
    quizId: "",
    result: null,
    evidence: null,
    plan: null,
    receipt: null,
    save: null,
    member: null,
    savedDone: false,
    phoneBinding: false,
    saveErrorMsg: "",
  },

  _report: null,
  _wentToRetest: false,

  onLoad: function (options) {
    var info = helpers.getWindowInfo();
    var section = String((options && options.section) || "result").trim();
    this.setData({
      isDark: helpers.isDarkOr("light"),
      statusBarHeight: info.statusBarHeight || 44,
      navHeight: (info.statusBarHeight || 44) + 44,
      section: SECTIONS[section] ? section : "result",
      quizId: String((options && options.quiz_id) || "").trim(),
      savedDone: section === "saved",
    });
    this._loadReport();
  },

  onShow: function () {
    surfaceTelemetry.trackModuleView(this, {
      module: "pass_readiness",
      section: "report_" + this.data.section,
    });
    this.setData({ isDark: helpers.isDarkOr("light") });
    // 从复测页返回 → 展示证明收据屏(收据文案不造判分结论, 判定归复测页服务端)
    if (this._wentToRetest && this.data.stage === "ready") {
      this._wentToRetest = false;
      this._switchSection("receipt");
    }
  },

  onHide: function () {
    surfaceTelemetry.trackModuleExit(this);
  },

  onUnload: function () {
    surfaceTelemetry.trackModuleExit(this);
  },

  // ── 报告加载: 快照优先, 服务端兜底 ─────────────────────────
  _loadReport: function () {
    var self = this;
    var snapshot = auth.readOwnerStorage
      ? auth.readOwnerStorage(passVm.REPORT_STORAGE_KEY)
      : null;
    if (
      snapshot &&
      snapshot.report &&
      (!self.data.quizId || snapshot.quizId === self.data.quizId)
    ) {
      self._applyReport(snapshot.quizId, snapshot.report);
      return;
    }
    if (self.data.quizId) {
      self._fetchReport(self.data.quizId);
      return;
    }
    // 无 quiz_id: 用 diagnostic_sources 找最近一次(唯一判断源)
    api
      .getAssessmentProfile({ noRetry: true })
      .then(function (payload) {
        var source = reportVm.readDiagnosticSource(payload);
        if (!source.completed || !source.quizId) {
          self.setData({ stage: "error", errorText: "还没有完成过过线体检，先做一次诊断吧" });
          return;
        }
        self._fetchReport(source.quizId);
      })
      .catch(function () {
        self.setData({ stage: "error", errorText: "报告加载失败，请稍后重试" });
      });
  },

  _fetchReport: function (quizId) {
    var self = this;
    api
      .getAssessmentReport(quizId)
      .then(function (resp) {
        self._applyReport(quizId, (resp && (resp.data || resp)) || {});
      })
      .catch(function (err) {
        var msg = api.describeRequestError
          ? api.describeRequestError(err, "报告加载失败，请稍后重试")
          : "报告加载失败，请稍后重试";
        self.setData({ stage: "error", errorText: msg });
      });
  },

  _applyReport: function (quizId, report) {
    this._report = report;
    var result = reportVm.buildResultModel(report);
    var pr = _obj(report.pass_readiness);
    this.setData({
      stage: "ready",
      quizId: String(quizId || ""),
      result: result,
      evidence: reportVm.buildEvidenceModel(report, result),
      plan: reportVm.buildPlanPreviewModel(null), // 二波接 exam_prep_plan_projection
      receipt: reportVm.buildReceiptModel(),
      member: reportVm.buildMembershipCta({
        daysToExam: pr.days_to_exam,
        passedSubjectLine: pr.passed_subject_line,
      }),
    });
    this._loadSaveModel();
  },

  // 保存屏形态: 手机号已知 → 直接保存态; openid-only → 二次授权(可拒, 不拦结果)
  _loadSaveModel: function () {
    var self = this;
    api
      .getUserInfo()
      .then(function (raw) {
        var info = api.unwrapResponse ? api.unwrapResponse(raw) : (raw && raw.data) || raw;
        var phone = String((info && info.phone) || "").replace(/\D/g, "");
        self.setData({ save: reportVm.buildSaveModel(phone.length >= 8) });
      })
      .catch(function () {
        self.setData({ save: reportVm.buildSaveModel(false) });
      });
  },

  // ── section 导航(每屏一个主 CTA) ────────────────────────────
  _switchSection: function (section) {
    if (!SECTIONS[section]) return;
    this.setData({ section: section });
    surfaceTelemetry.trackModuleView(this, {
      module: "pass_readiness",
      section: "report_" + section,
    });
  },

  onPrimaryCta: function () {
    // 屏3 → 屏4: 先补最影响得分的这一点
    trackBehavior("learning_action_started", {
      module: "pass_readiness",
      action: "open",
      objectType: "pass_readiness_evidence",
      objectId: this.data.quizId,
    });
    this._switchSection("evidence");
  },

  onEvidenceContinue: function () {
    this._switchSection("plan");
  },

  onPlanContinue: function () {
    this._switchSection("save");
  },

  onReceiptContinue: function () {
    this._switchSection("save");
  },

  onBackToResult: function () {
    this._switchSection("result");
  },

  // 屏 6: 跳既有微课页(无绑定则按钮不渲染, 禁 dead button)
  onOpenLesson: function (e) {
    var packId = String((e.currentTarget.dataset || {}).packId || "").trim();
    if (!packId) return;
    trackBehavior("learning_action_started", {
      module: "pass_readiness",
      action: "start_lesson",
      objectType: "lesson",
      objectId: packId,
    });
    wx.navigateTo({ url: route.lubanStation(packId) });
  },

  // 屏 7: 跳既有复测页; 返回后本页展示证明收据屏
  onOpenRetest: function (e) {
    var packId = String((e.currentTarget.dataset || {}).packId || "").trim();
    if (!packId) return;
    trackBehavior("learning_action_started", {
      module: "pass_readiness",
      action: "start_retest",
      objectType: "retest",
      objectId: packId,
    });
    this._wentToRetest = true;
    wx.navigateTo({
      url: "/packageDeeptutor/pages/luban/retest/retest?pack_id=" + encodeURIComponent(packId),
    });
  },

  // 屏 8: openid-only 学员的二次手机号授权(拒绝零弹窗零 toast, 结果不拦)
  handleSavePhoneNumber: function (e) {
    var self = this;
    if (self.data.phoneBinding) return;
    var lane = passVm.resolveLoginLane(e && e.detail);
    trackBehavior("auth_authorize_clicked", {
      module: "pass_readiness",
      action: "authorize",
      objectType: "phone_auth_save",
      result: lane.lane === "phone" ? "granted" : "denied",
    });
    if (lane.lane !== "phone") {
      // 拒绝: 什么都不弹, declineNote 常驻可见, 继续看结果
      return;
    }
    self.setData({ phoneBinding: true, saveErrorMsg: "" });
    api
      .bindPhone(lane.phoneCode)
      .then(function () {
        trackBehavior("learning_action_completed", {
          module: "pass_readiness",
          action: "complete",
          objectType: "pass_readiness_report_saved",
          objectId: self.data.quizId,
          result: "success",
        });
        self.setData({
          phoneBinding: false,
          save: reportVm.buildSaveModel(true),
        });
        self._landAfterSave();
      })
      .catch(function (err) {
        var msg = api.describeRequestError
          ? api.describeRequestError(err, "绑定失败，请重试")
          : "绑定失败，请重试";
        self.setData({ phoneBinding: false, saveErrorMsg: msg });
      });
  },

  // 屏 8(已有手机号): 直接确认保存 → 参数化落点
  onSaveDirect: function () {
    trackBehavior("learning_action_completed", {
      module: "pass_readiness",
      action: "complete",
      objectType: "pass_readiness_report_saved",
      objectId: this.data.quizId,
      result: "success",
    });
    this._landAfterSave();
  },

  // 完成后落点收口(跑道反转第 1 步, 已接线):
  // 落点常量 = pass-readiness-view-model.postDiagnosticLandingRoute → 计划页
  // (跑道视图, G 线冻结路由)。计划页代码在 G 线分支, 汇合前 redirect 会失败,
  // fail 回退到本页保存成功态; 汇合后自动连通, 本函数零改动。
  _landAfterSave: function () {
    var self = this;
    var target = passVm.postDiagnosticLandingRoute(this.data.quizId);
    if (target.indexOf("pages/luban/pass-readiness/report/report") >= 0) {
      this.setData({ savedDone: true, section: "saved" });
      return;
    }
    wx.redirectTo({
      url: target,
      fail: function () {
        self.setData({ savedDone: true, section: "saved" });
      },
    });
  },

  onSavedContinue: function () {
    this._switchSection("member");
  },

  // 屏 9: 会员 handoff → 既有会员面
  onMembershipCta: function () {
    trackBehavior("learning_action_started", {
      module: "pass_readiness",
      action: "open",
      objectType: "membership",
      objectId: this.data.quizId,
    });
    wx.navigateTo({ url: route.billing() });
  },

  onRetry: function () {
    this.setData({ stage: "loading", errorText: "" });
    this._loadReport();
  },

  onStartNewDiagnostic: function () {
    wx.redirectTo({ url: route.lubanPassReadinessExam() });
  },

  goBack: function () {
    if (this.data.section !== "result" && this.data.stage === "ready") {
      this._switchSection("result");
      return;
    }
    wx.navigateBack({
      delta: 1,
      fail: function () {
        wx.reLaunch({ url: route.lubanPassReadiness() });
      },
    });
  },
});
