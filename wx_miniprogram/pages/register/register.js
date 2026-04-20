var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");

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
      api
        .getUserInfo()
        .then(function () {
          wx.switchTab({ url: "/pages/chat/chat" });
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
        auth.setToken(token);
        wx.switchTab({ url: "/pages/chat/chat" });
      })
      .catch(function (err) {
        var m = String((err && err.message) || "");
        var msg = "注册失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("429")) msg = "注册过于频繁，请稍后再试";
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
  goLogin: function () {
    wx.navigateBack({
      fail: function () {
        wx.redirectTo({ url: "/pages/login/login" });
      },
    });
  },
  _completeWechatAuth: function (payload) {
    var inner = payload && (payload.data || payload);
    var token = inner && inner.token;
    if (!token) throw new Error("服务端未返回凭证");
    auth.setToken(token);
  },
  handleWechatRegister: function () {
    var self = this;
    if (self.data.wechatLoading || self.data.loading) return;
    self.setData({ wechatLoading: true, errorMsg: "" });
    wx.login({
      success: function (loginRes) {
        if (!loginRes.code) {
          self.setData({ wechatLoading: false, errorMsg: "微信登录失败，请重试" });
          return;
        }
        api
          .wxLogin(loginRes.code)
          .then(function (resp) {
            self._completeWechatAuth(resp);
          })
          .then(function () {
            wx.switchTab({ url: "/pages/chat/chat" });
          })
          .catch(function (err) {
            var m = String((err && err.message) || "");
            var msg = "微信快捷注册失败，请重试";
            if (m.includes("credentials")) msg = "后端未配置微信小程序密钥";
            else if (m.includes("NETWORK_")) msg = "网络连接失败";
            else if (m && !m.startsWith("HTTP_")) msg = m;
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
      fail: function () {
        self.setData({ wechatLoading: false, errorMsg: "无法获取微信登录凭证" });
      },
    });
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
    wx.login({
      success: function (loginRes) {
        if (!loginRes.code) {
          self.setData({ wechatLoading: false, errorMsg: "微信登录失败，请重试" });
          return;
        }
        api
          .wxLogin(loginRes.code)
          .then(function (resp) {
            self._completeWechatAuth(resp);
            return api.bindPhone(phoneCode);
          })
          .then(function (resp) {
            var inner = resp.data || resp;
            if (inner && inner.token) {
              auth.setToken(inner.token);
            }
            wx.switchTab({ url: "/pages/chat/chat" });
          })
          .catch(function (err) {
            var m = String((err && err.message) || "");
            var msg = "微信快捷注册失败，请重试";
            if (m.includes("credentials")) msg = "后端未配置微信小程序密钥";
            else if (m.includes("getuserphonenumber")) msg = "微信手机号授权失败";
            else if (m.includes("NETWORK_")) msg = "网络连接失败";
            else if (m && !m.startsWith("HTTP_")) msg = m;
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
      fail: function () {
        self.setData({ wechatLoading: false, errorMsg: "无法获取微信登录凭证" });
      },
    });
  },
});
