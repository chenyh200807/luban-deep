var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");

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
  },

  onLoad: function () {
    try {
      var info = helpers.getWindowInfo();
      var sb = info.safeArea ? info.screenHeight - info.safeArea.bottom : 0;
      this.setData({
        statusBarHeight: info.statusBarHeight || 44,
        safeBottom: sb,
        isDark: helpers.isDark(),
      });
    } catch (_) {}
    if (auth.isLoggedIn()) {
      wx.switchTab({ url: "/pages/chat/chat" });
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

  togglePassword: function () {
    this.setData({ showPassword: !this.data.showPassword });
  },

  switchLoginMode: function () {
    this.setData({
      loginMode: this.data.loginMode === "password" ? "phone_code" : "password",
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
          self.setData({ codeCountdown: retryAfter, loading: false });
          self._startCountdown(retryAfter);
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
        wx.switchTab({ url: "/pages/chat/chat" });
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
        wx.switchTab({ url: "/pages/chat/chat" });
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
    wx.navigateBack({
      fail: function () {
        wx.redirectTo({ url: "/pages/login/login" });
      },
    });
  },

  goRegister: function () {
    wx.navigateTo({ url: "/pages/register/register" });
  },
});
