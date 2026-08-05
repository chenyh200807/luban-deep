// 过线体检(S5)· 屏 1 落地页
// §4.1 六要素 + §5.1 登录 UI 合同(验收级):
// - 入口唯一按钮「微信一键登录 · 开始测评」(open-type=getPhoneNumber);
// - 用户在微信弹窗点「拒绝」→ 同一 handler 内直接走 login-basic 继续进测评:
//   零二次弹窗、零挽留文案、零 toast, 拒绝路径与授权路径 tap 数相同;
// - 登录失败(微信 API 错误, 非拒绝)才展示重试, 埋点区分 decline 与 failure。
var api = require("../../../../utils/api");
var auth = require("../../../../utils/auth");
var helpers = require("../../../../utils/helpers");
var route = require("../../../../utils/route");
var surfaceTelemetry = require("../../../../utils/surface-telemetry");
var passVm = require("../../../../utils/pass-readiness-view-model");
var reportVm = require("../../../../utils/pass-readiness-report-view-model");

function trackBehavior(eventName, payload) {
  if (surfaceTelemetry && typeof surfaceTelemetry.trackProductBehavior === "function") {
    surfaceTelemetry.trackProductBehavior(eventName, payload);
  }
}

Page({
  data: {
    isDark: false,
    statusBarHeight: 44,
    navHeight: 96,
    safeBottom: 0,
    copy: passVm.LANDING_COPY,
    loggedIn: false,
    logging: false,
    errorMsg: "",
    entrySource: "",
    privacyChecked: false,
    privacyContractName: "《用户隐私保护指引》",
    // 老学员入口(§5.3): 唯一判断源 = /assessment/profile diagnostic_sources
    lastDiagnostic: { completed: false, quizId: "", scoredAt: "" },
  },

  onLoad: function (options) {
    var info = helpers.getWindowInfo();
    this.setData({
      isDark: helpers.isDarkOr("light"),
      statusBarHeight: info.statusBarHeight || 44,
      navHeight: (info.statusBarHeight || 44) + 44,
      safeBottom: info.safeArea ? info.screenHeight - info.safeArea.bottom : 0,
      entrySource: String((options && (options.entry_source || options.source)) || "").trim(),
      loggedIn: auth.isLoggedIn(),
    });
    this._refreshPrivacySetting();
    this._loadDiagnosticSource();
  },

  onShow: function () {
    surfaceTelemetry.trackModuleView(this, {
      module: "pass_readiness",
      section: "landing",
    });
    this.setData({ isDark: helpers.isDarkOr("light"), loggedIn: auth.isLoggedIn() });
  },

  onHide: function () {
    surfaceTelemetry.trackModuleExit(this);
  },

  onUnload: function () {
    surfaceTelemetry.trackModuleExit(this);
  },

  _loadDiagnosticSource: function () {
    var self = this;
    if (!auth.isLoggedIn() || !api.getAssessmentProfile) return;
    api
      .getAssessmentProfile({ noRetry: true })
      .then(function (payload) {
        self.setData({ lastDiagnostic: reportVm.readDiagnosticSource(payload) });
      })
      .catch(function () {
        // 读不到就当无历史; 不阻塞入口
      });
  },

  _refreshPrivacySetting: function () {
    var self = this;
    if (typeof wx.getPrivacySetting !== "function") {
      self.setData({ privacyChecked: true });
      return;
    }
    wx.getPrivacySetting({
      success: function (res) {
        self.setData({
          privacyChecked: !(res && res.needAuthorization),
          privacyContractName:
            (res && res.privacyContractName) || "《用户隐私保护指引》",
        });
      },
    });
  },

  handlePrivacyAgreementAuthorized: function () {
    this.setData({ privacyChecked: true, errorMsg: "" });
  },

  handlePrivacyRequiredTap: function () {
    this.setData({ errorMsg: "请先勾选同意用户隐私保护指引后继续" });
  },

  openPrivacyGuide: function () {
    wx.navigateTo({ url: route.terms() });
  },

  // 已登录: 单按钮直接进测评(与登录路径同为一次点击)
  onStartTap: function () {
    if (this.data.logging) return;
    trackBehavior("learning_action_started", {
      module: "pass_readiness",
      action: "start_probe",
      objectType: "pass_readiness_entry",
      objectId: "logged_in",
    });
    this._enterExam();
  },

  // §5.1 唯一 handler: 授权(phone_code)与拒绝(login-basic)在此分车道。
  handlePhoneNumber: function (e) {
    var self = this;
    if (self.data.logging) return;
    var lane = passVm.resolveLoginLane(e && e.detail);
    trackBehavior("auth_authorize_clicked", {
      module: "pass_readiness",
      action: "authorize",
      objectType: "phone_auth",
      result: lane.lane === "phone" ? "granted" : "denied",
    });
    if (lane.privacyInterrupted) {
      // 隐私协议中断 ≠ 拒绝手机号: 不能静默替用户登录, 提示重新勾选
      self.setData({ privacyChecked: false, errorMsg: "请先勾选同意用户隐私保护指引后继续" });
      self._refreshPrivacySetting();
      return;
    }
    self.setData({ logging: true, errorMsg: "" });
    self
      ._requestWxLoginCode()
      .then(function (code) {
        return lane.lane === "phone"
          ? api.wxLoginWithPhone(code, lane.phoneCode)
          : api.wxLoginBasic(code);
      })
      .then(function (resp) {
        var inner = (resp && (resp.data || resp)) || {};
        var token = inner.token;
        if (!token) throw new Error("服务端未返回凭证");
        auth.setToken(token, inner.expires_at, inner);
        trackBehavior("auth_result", {
          module: "pass_readiness",
          action: "complete",
          objectType: lane.lane === "phone" ? "phone_auth" : "openid_basic",
          result: "success",
        });
        self.setData({ logging: false, loggedIn: true });
        // 授权/拒绝两条路径在此汇合, 同样直接进测评(零二次弹窗/零 toast)
        self._enterExam();
      })
      .catch(function (err) {
        // 登录失败(非拒绝): 埋点区分 login_failed, 页面内联展示可重试
        trackBehavior("auth_result", {
          module: "pass_readiness",
          action: "error",
          objectType: "login_failed",
          result: "fail",
          errorCode: String((err && err.message) || "").slice(0, 60),
        });
        var msg = api.describeRequestError
          ? api.describeRequestError(err, "登录失败，请重试", { context: "wechat_login" })
          : "登录失败，请重试";
        self.setData({ logging: false, errorMsg: msg });
      });
  },

  _requestWxLoginCode: function () {
    return new Promise(function (resolve, reject) {
      wx.login({
        success: function (res) {
          if (res && res.code) resolve(res.code);
          else reject(new Error("WX_LOGIN_CODE_MISSING"));
        },
        fail: function () {
          reject(new Error("WX_LOGIN_FAILED"));
        },
      });
    });
  },

  _enterExam: function () {
    wx.navigateTo({
      url: route.lubanPassReadinessExam(
        this.data.entrySource ? { entry_source: this.data.entrySource } : null,
      ),
    });
  },

  // 老学员: 查看上次报告(新测不覆盖旧报告, §5.3)
  onViewLastReport: function () {
    if (!this.data.lastDiagnostic.completed) return;
    wx.navigateTo({
      url: route.lubanPassReadinessReport({ quiz_id: this.data.lastDiagnostic.quizId }),
    });
  },

  goBack: function () {
    wx.navigateBack({
      delta: 1,
      fail: function () {
        wx.reLaunch({ url: route.chat() });
      },
    });
  },
});
