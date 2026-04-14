var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    loading: false,
    wechatLoading: false,
    errorMsg: "",
    username: "",
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
  onPhoneCodeInput: function (e) {
    this.setData({ phoneCode: e.detail.value, errorMsg: "" });
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
        // resp.code is the outer ApiResponse code; inner may be the nested data
        var outerCode = resp.code !== undefined ? resp.code : inner.code;
        var outerMsg = resp.message || inner.message || "发送失败";
        var dataObj = inner.data || inner;
        var retryAfter =
          (dataObj && dataObj.retry_after) || inner.retry_after || 60;
        var sent = inner.sent || (dataObj && dataObj.sent);

        if (outerCode === 0 || sent) {
          // Success: start countdown
          self.setData({ codeCountdown: retryAfter, loading: false });
          self._startCountdown(retryAfter);
        } else {
          // Error: show message, do NOT start countdown
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
  handleRegister: function () {
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
        if (!token) throw new Error(resp.error || resp.message || "注册失败");
        auth.setToken(token, userId);
        wx.switchTab({ url: "/pages/chat/chat" });
      })
      .catch(function (err) {
        var m = String(err.message || "");
        var msg = "注册失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("400") || m.includes("验证码"))
          msg = "验证码错误或已过期";
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
  goLogin: function () {
    wx.navigateBack({
      fail: function () {
        wx.redirectTo({ url: "/pages/login/login" });
      },
    });
  },
  _completeWechatAuth: function (payload) {
    var inner = payload && (payload.data || payload);
    var user = (inner && inner.user) || {};
    var token = inner && inner.token;
    var userId = user.id || user.user_id || inner.id;
    if (!token) throw new Error("服务端未返回凭证");
    auth.setToken(token, userId);
  },
  _bindPhoneAfterWechat: function () {
    var phone = (this.data.username || "").trim();
    if (!phone || phone.length < 11) return Promise.resolve();
    return api
      .bindPhone(phone)
      .then(function (resp) {
        var inner = resp.data || resp;
        if (inner && inner.token) {
          var user = inner.user || {};
          auth.setToken(inner.token, user.id || user.user_id);
        }
      });
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
            return self._bindPhoneAfterWechat();
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
    var phoneCode =
      e &&
      e.detail &&
      (e.detail.code || e.detail.phoneCode || "");
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
              var user = inner.user || {};
              auth.setToken(inner.token, user.id || user.user_id);
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
