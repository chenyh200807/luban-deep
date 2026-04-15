var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");
var route = require("../../utils/route");
var analytics = require("../../../utils/analytics");

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    loading: false,
    errorMsg: "",
    username: "",
    password: "",
    showPassword: false,
    loginMode: "phone_code",
    phoneCode: "",
    codeCountdown: 0,
    isDark: true,
    entrySource: "",
    returnTo: "",
  },

  onLoad: function (options) {
    try {
      var info = helpers.getWindowInfo();
      var sb = info.safeArea ? info.screenHeight - info.safeArea.bottom : 0;
      this.setData({
        statusBarHeight: info.statusBarHeight || 44,
        safeBottom: sb,
        isDark: helpers.isDark(),
      });
    } catch (_) {}
    this._captureEntryContext(options);
    if (auth.isLoggedIn()) {
      var self = this;
      api
        .getUserInfo()
        .then(function () {
          self._reLaunchAfterAuth();
        })
        .catch(function () {
          auth.clearToken();
        });
    }
  },

  onUnload: function () {
    if (this._codeTimer) {
      clearInterval(this._codeTimer);
      this._codeTimer = null;
    }
  },

  onUsernameInput: function (e) {
    this.setData({ username: e.detail.value, errorMsg: "" });
  },

  onPasswordInput: function (e) {
    this.setData({ password: e.detail.value, errorMsg: "" });
  },

  onPhoneCodeInput: function (e) {
    this.setData({ phoneCode: e.detail.value, errorMsg: "" });
  },

  _captureEntryContext: function (options) {
    var source =
      (options && (options.entrySource || options.entry_source || options.source)) ||
      "";
    var returnTo = route.resolveInternalUrl(
      options && options.returnTo,
      route.chat(source ? { entry_source: source } : null),
    );
    this.setData({
      entrySource: String(source || "").trim(),
      returnTo: returnTo,
    });
  },

  _reLaunchAfterAuth: function () {
    var source = this.data.entrySource;
    var fallback = route.chat(source ? { entry_source: source } : null);
    wx.reLaunch({
      url: route.resolveInternalUrl(this.data.returnTo, fallback),
    });
  },

  _trackLoginSuccess: function (method) {
    analytics.track("deeptutor_login_success", {
      login_method: method,
      entry_source: this.data.entrySource,
      return_to: this.data.returnTo,
      page: "manual_login",
    });
  },

  togglePassword: function () {
    this.setData({ showPassword: !this.data.showPassword });
  },

  switchLoginMode: function (e) {
    var nextMode =
      e &&
      e.currentTarget &&
      e.currentTarget.dataset &&
      e.currentTarget.dataset.mode;
    if (!nextMode) {
      nextMode = this.data.loginMode === "password" ? "phone_code" : "password";
    }
    if (nextMode === this.data.loginMode) {
      return;
    }
    this.setData({
      loginMode: nextMode,
      errorMsg: "",
    });
  },

  sendCode: function () {
    var self = this;
    if (self.data.codeCountdown > 0 || self.data.loading) return;
    var phone = (self.data.username || "").trim();
    if (!phone || phone.length < 11) {
      self.setData({ errorMsg: "请输入正确的手机号" });
      return;
    }
    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/send-code",
        method: "POST",
        data: { phone: phone },
        noAuth: true,
      })
      .then(function (resp) {
        var inner = resp.data || resp;
        var outerCode = resp.code !== undefined ? resp.code : inner.code;
        var outerMsg = resp.message || inner.message || "发送失败";
        var dataObj = inner.data || inner;
        var retryAfter = (dataObj && dataObj.retry_after) || inner.retry_after || 60;
        var sent = inner.sent || (dataObj && dataObj.sent);

        if (outerCode === 0 || sent) {
          var debugCode = (dataObj && dataObj.debug_code) || inner.debug_code || "";
          var nextData = { codeCountdown: retryAfter, loading: false };
          if (debugCode) nextData.phoneCode = debugCode;
          self.setData(nextData);
          self._startCountdown(retryAfter);
          if (debugCode) {
            wx.showModal({
              title: "测试验证码",
              content: "当前环境未接短信服务，验证码：" + debugCode,
              showCancel: false,
            });
          }
        } else {
          self.setData({ errorMsg: outerMsg, loading: false });
        }
      })
      .catch(function (err) {
        var m = String(err.message || "");
        var msg = "发送失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("429")) msg = "发送过于频繁，请稍后再试";
        self.setData({ errorMsg: msg, loading: false });
      });
  },

  _startCountdown: function (seconds) {
    var self = this;
    if (self._codeTimer) clearInterval(self._codeTimer);
    var remaining = seconds;
    self._codeTimer = setInterval(function () {
      remaining--;
      if (remaining <= 0) {
        clearInterval(self._codeTimer);
        self._codeTimer = null;
      }
      self.setData({ codeCountdown: remaining });
    }, 1000);
  },

  verifyCode: function () {
    var self = this;
    var phone = (self.data.username || "").trim();
    var code = (self.data.phoneCode || "").trim();
    if (!phone || !code) {
      self.setData({ errorMsg: "请输入手机号和验证码" });
      return;
    }
    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/verify-code",
        method: "POST",
        data: { phone: phone, code: code },
        noAuth: true,
      })
      .then(function (resp) {
        var inner = resp.data || resp;
        var user = inner.user || {};
        var token = inner.token;
        var userId = user.id || inner.id;
        if (!token) throw new Error(resp.error || resp.message || "验证失败");
        auth.setToken(token, userId);
        self._trackLoginSuccess("phone_code");
        self._reLaunchAfterAuth();
      })
      .catch(function (err) {
        var m = String(err.message || "");
        var msg = "验证失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("400") || m.includes("验证码")) msg = "验证码错误或已过期";
        else if (m.includes("429")) msg = "操作过于频繁";
        else if (m && !m.startsWith("HTTP_")) msg = m;
        self.setData({ errorMsg: msg });
      })
      .then(
        function () {
          self.setData({ loading: false });
        },
        function () {
          self.setData({ loading: false });
        },
      );
  },

  handlePasswordLogin: function () {
    if (this.data.loading) return;
    var self = this;
    var u = self.data.username;
    var p = self.data.password;
    if (!u || !u.trim()) return self.setData({ errorMsg: "请输入用户名" });
    if (!p) return self.setData({ errorMsg: "请输入密码" });
    if (p.length < 6) return self.setData({ errorMsg: "密码至少 6 位" });
    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/login",
        method: "POST",
        data: { username: u.trim(), password: p },
        noAuth: true,
      })
      .then(function (resp) {
        var inner = resp.data || resp;
        var user = inner.user || resp.user || {};
        var token = inner.token || inner._token || resp.token || resp._token || user._token;
        var userId = user.id || inner.id || resp.id;
        if (!token) throw new Error(resp.error || resp.message || "登录失败");
        auth.setToken(token, userId);
        self._trackLoginSuccess("password");
        self._reLaunchAfterAuth();
      })
      .catch(function (err) {
        var m = String(err.message || "");
        var msg = "登录失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("401") || m.includes("密码")) msg = "用户名或密码错误";
        else if (m.includes("429")) msg = "登录过于频繁";
        else if (m.includes("token")) msg = "服务端未返回凭证";
        else if (m && !m.startsWith("HTTP_")) msg = m;
        self.setData({ errorMsg: msg });
      })
      .then(
        function () {
          self.setData({ loading: false });
        },
        function () {
          self.setData({ loading: false });
        },
      );
  },

  goBack: function () {
    var fallbackUrl = route.login({
      entrySource: this.data.entrySource,
      returnTo: this.data.returnTo,
    });
    wx.navigateBack({
      fail: function () {
        wx.reLaunch({ url: fallbackUrl });
      },
    });
  },

  goRegister: function () {
    wx.navigateTo({
      url: route.register({
        entrySource: this.data.entrySource,
        returnTo: this.data.returnTo,
      }),
    });
  },
});
