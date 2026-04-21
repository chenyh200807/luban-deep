var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");
var route = require("../../utils/route");
var analytics = require("../../utils/analytics");

var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
var CN_MOBILE_RE = /^1[3-9]\d{9}$/;

function validateRegisterForm(username, phone, password, confirmPassword) {
  if (!username) return "请输入用户名或邮箱";
  if (username.length < 2) return "账号至少需要 2 个字符";
  if (username.length > 50) return "账号不能超过 50 个字符";
  if (username.indexOf("@") >= 0 && !EMAIL_RE.test(username)) {
    return "邮箱格式不正确";
  }
  if (!phone) return "请输入手机号";
  if (!CN_MOBILE_RE.test(phone)) return "请输入正确的手机号";
  if (!password) return "请设置密码";
  if (password.length < 6) return "密码至少 6 位";
  if (password.length > 128) return "密码不能超过 128 个字符";
  if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password)) {
    return "密码需包含大写字母、小写字母和数字";
  }
  if (!confirmPassword) return "请再次输入密码";
  if (password !== confirmPassword) return "两次输入的密码不一致";
  return "";
}

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    loading: false,
    wechatLoading: false,
    errorMsg: "",
    username: "",
    phone: "",
    password: "",
    confirmPassword: "",
    showPassword: false,
    showConfirmPassword: false,
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
        .catch(function (err) {
          if (String((err && err.message) || "") === "AUTH_EXPIRED") {
            auth.clearToken();
          }
        });
    }
  },
  onUsernameInput: function (e) {
    this.setData({ username: e.detail.value, errorMsg: "" });
  },
  onPhoneInput: function (e) {
    this.setData({ phone: e.detail.value, errorMsg: "" });
  },
  onPasswordInput: function (e) {
    this.setData({ password: e.detail.value, errorMsg: "" });
  },
  onConfirmPasswordInput: function (e) {
    this.setData({ confirmPassword: e.detail.value, errorMsg: "" });
  },
  togglePassword: function () {
    this.setData({ showPassword: !this.data.showPassword });
  },
  toggleConfirmPassword: function () {
    this.setData({ showConfirmPassword: !this.data.showConfirmPassword });
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
      page: "register",
    });
  },
  _describeAuthError: function (err, fallbackMsg, options) {
    if (!api || typeof api.describeRequestError !== "function") {
      return fallbackMsg;
    }
    return api.describeRequestError(err, fallbackMsg, options || {});
  },
  _requestWechatSession: function (attempt) {
    var self = this;
    var currentAttempt = Number(attempt) || 0;
    return new Promise(function (resolve, reject) {
      wx.login({
        success: function (loginRes) {
          if (!loginRes.code) {
            reject(new Error("WX_LOGIN_CODE_MISSING"));
            return;
          }
          api
            .wxLogin(loginRes.code)
            .then(resolve)
            .catch(function (err) {
              if (
                currentAttempt < 1 &&
                typeof api.shouldRetryWechatLogin === "function" &&
                api.shouldRetryWechatLogin(err)
              ) {
                self._requestWechatSession(currentAttempt + 1).then(resolve).catch(reject);
                return;
              }
              reject(err);
            });
        },
        fail: function () {
          reject(new Error("WX_LOGIN_FAILED"));
        },
      });
    });
  },
  handleRegister: function () {
    var self = this;
    if (self.data.loading) return;
    var username = (self.data.username || "").trim();
    var phone = (self.data.phone || "").trim();
    var password = self.data.password || "";
    var confirmPassword = self.data.confirmPassword || "";
    var formError = validateRegisterForm(username, phone, password, confirmPassword);

    if (formError) {
      self.setData({ errorMsg: formError });
      return;
    }

    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/register",
        method: "POST",
        data: {
          username: username,
          password: password,
          phone: phone,
        },
        noAuth: true,
      })
      .then(function (resp) {
        var inner = resp.data || resp;
        var user = inner.user || resp.user || {};
        var token = inner.token || inner._token || resp.token || resp._token || user._token;
        if (!token) throw new Error("服务端未返回凭证");
        auth.setToken(token, inner.expires_at);
        self._trackLoginSuccess("register_password");
        self._reLaunchAfterAuth();
      })
      .catch(function (err) {
        var msg = self._describeAuthError(err, "注册失败，请重试", {
          customMap: function (info) {
            if (info.status === 429) {
              return "注册过于频繁，请稍后再试";
            }
            return "";
          },
        });
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
  goLogin: function () {
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
  _completeWechatAuth: function (payload) {
    var inner = payload && (payload.data || payload);
    var token = inner && inner.token;
    if (!token) throw new Error("服务端未返回凭证");
    auth.setToken(token, inner && inner.expires_at);
  },
  handleWechatRegister: function () {
    var self = this;
    if (self.data.wechatLoading || self.data.loading) return;
    self.setData({ wechatLoading: true, errorMsg: "" });
    self
      ._requestWechatSession(0)
      .then(function (resp) {
        self._completeWechatAuth(resp);
      })
      .then(function () {
        self._trackLoginSuccess("register_wechat");
        self._reLaunchAfterAuth();
      })
      .catch(function (err) {
        var msg = self._describeAuthError(err, "微信快捷注册失败，请重试", {
          context: "wechat_login",
          customMap: function (info) {
            if (
              info.rawMessage.indexOf("credentials") >= 0 ||
              info.detailText.indexOf("credentials") >= 0
            ) {
              return "后端未配置微信小程序密钥";
            }
            if (
              info.rawMessage.indexOf("WX_LOGIN_") >= 0 ||
              info.detailText.indexOf("WX_LOGIN_") >= 0
            ) {
              return "无法获取微信登录凭证";
            }
            return "";
          },
        });
        self.setData({ errorMsg: msg });
      })
      .then(
        function () {
          self.setData({ wechatLoading: false });
        },
        function () {
          self.setData({ wechatLoading: false });
        },
      );
  },
  handleWechatPhoneNumber: function (e) {
    var self = this;
    if (self.data.wechatLoading || self.data.loading) return;
    var phoneCode = e && e.detail && (e.detail.code || e.detail.phoneCode || "");
    if (!phoneCode) {
      self.setData({ errorMsg: "未获取到微信手机号授权" });
      return;
    }
    self.setData({ wechatLoading: true, errorMsg: "" });
    self
      ._requestWechatSession(0)
      .then(function (resp) {
        self._completeWechatAuth(resp);
        return api.bindPhone(phoneCode);
      })
      .then(function (resp) {
        var inner = resp.data || resp;
        if (inner && inner.token) {
          auth.setToken(inner.token, inner.expires_at);
        }
        self._trackLoginSuccess("register_wechat_phone");
        self._reLaunchAfterAuth();
      })
      .catch(function (err) {
        var msg = self._describeAuthError(err, "微信快捷注册失败，请重试", {
          context: "wechat_login",
          customMap: function (info) {
            if (
              info.rawMessage.indexOf("credentials") >= 0 ||
              info.detailText.indexOf("credentials") >= 0
            ) {
              return "后端未配置微信小程序密钥";
            }
            if (info.detailText.toLowerCase().indexOf("getuserphonenumber") >= 0) {
              return "微信手机号授权失败";
            }
            if (
              info.rawMessage.indexOf("WX_LOGIN_") >= 0 ||
              info.detailText.indexOf("WX_LOGIN_") >= 0
            ) {
              return "无法获取微信登录凭证";
            }
            return "";
          },
        });
        self.setData({ errorMsg: msg });
      })
      .then(
        function () {
          self.setData({ wechatLoading: false });
        },
        function () {
          self.setData({ wechatLoading: false });
        },
      );
  },
});
