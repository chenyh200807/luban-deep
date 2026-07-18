var api = require("../../utils/api");
var helpers = require("../../utils/helpers");
var route = require("../../utils/route");
var analytics = require("../../utils/analytics");

var CN_MOBILE_RE = /^1[3-9]\d{9}$/;

function canShowDebugCode() {
  var cfg = typeof __wxConfig !== "undefined" ? __wxConfig : {};
  return cfg.platform === "devtools" || cfg.envVersion === "develop" || cfg.envVersion === "trial";
}

function showSmsSentFeedback(message) {
  wx.showToast({
    title: message || "验证码发送成功",
    icon: "none",
  });
}

function validateResetForm(username, phone, code, password, confirmPassword) {
  if (username && username.length < 2) return "账号至少需要 2 个字符";
  if (username && username.length > 50) return "账号不能超过 50 个字符";
  if (!phone) return "请输入手机号";
  if (!CN_MOBILE_RE.test(phone)) return "请输入正确的手机号";
  if (!code) return "请输入验证码";
  if (code.length !== 6) return "请输入 6 位验证码";
  if (!password) return "请设置新密码";
  if (password.length < 6) return "密码至少 6 位";
  if (password.length > 128) return "密码不能超过 128 个字符";
  if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password)) {
    return "密码需包含大写字母、小写字母和数字";
  }
  if (!confirmPassword) return "请再次输入新密码";
  if (password !== confirmPassword) return "两次输入的密码不一致";
  return "";
}

function describeResetAuthError(info) {
  var detail = String((info && info.detailText) || "").trim();
  if (info && info.status === 429) {
    return "操作过于频繁，请稍后再试";
  }
  if (!info || info.status !== 400) {
    return "";
  }
  if (detail.indexOf("账号或手机号不匹配") >= 0) {
    return "账号和手机号不匹配；快速登录用户可只填手机号重试";
  }
  if (detail.indexOf("验证码不存在") >= 0) {
    return "请先获取验证码";
  }
  if (detail.indexOf("验证码已过期") >= 0) {
    return "验证码已过期，请重新获取";
  }
  if (detail.indexOf("验证码错误次数过多") >= 0) {
    return "验证码错误次数过多，请重新获取验证码";
  }
  if (detail.indexOf("验证码错误") >= 0) {
    return "验证码错误，请重新输入";
  }
  if (detail.indexOf("手机号格式不正确") >= 0) {
    return "请输入正确的手机号";
  }
  return "信息填写有误，请检查后重试";
}

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    loading: false,
    errorMsg: "",
    username: "",
    phone: "",
    phoneCode: "",
    password: "",
    confirmPassword: "",
    showPassword: false,
    showConfirmPassword: false,
    codeCountdown: 0,
    entrySource: "",
    returnTo: "",
  },

  onLoad: function (options) {
    this.setData({ isDark: helpers.isDarkOr("light") });
    try {
      var info = helpers.getWindowInfo();
      var sb = info.safeArea ? info.screenHeight - info.safeArea.bottom : 0;
      this.setData({
        statusBarHeight: info.statusBarHeight || 44,
        safeBottom: sb,
      });
    } catch (_) {}
    this._captureEntryContext(options);
  },

  onUnload: function () {
    if (this._codeTimer) {
      clearInterval(this._codeTimer);
      this._codeTimer = null;
    }
  },

  _captureEntryContext: function (options) {
    var source =
      (options && (options.entrySource || options.entry_source || options.source)) ||
      "";
    var returnTo = route.resolveInternalUrl(
      options && options.returnTo,
      route.chat(source ? { entry_source: source } : null),
    );
    var nextData = {
      entrySource: String(source || "").trim(),
      returnTo: returnTo,
    };
    var username = String((options && options.username) || "").trim();
    if (username) nextData.username = username;
    this.setData(nextData);
  },

  _describeAuthError: function (err, fallbackMsg, options) {
    if (!api || typeof api.describeRequestError !== "function") {
      return fallbackMsg;
    }
    return api.describeRequestError(err, fallbackMsg, options || {});
  },

  _trackResetEvent: function (eventName, extra) {
    analytics.track(eventName, Object.assign(
      {
        entry_source: this.data.entrySource,
        return_to: this.data.returnTo,
        page: "reset_password",
      },
      extra || {},
    ));
  },

  onUsernameInput: function (e) {
    this.setData({ username: e.detail.value, errorMsg: "" });
  },

  onPhoneInput: function (e) {
    this.setData({ phone: e.detail.value, errorMsg: "" });
  },

  onPhoneCodeInput: function (e) {
    this.setData({ phoneCode: e.detail.value, errorMsg: "" });
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

  sendCode: function () {
    var self = this;
    if (self.data.codeCountdown > 0 || self.data.loading) return;
    var username = (self.data.username || "").trim();
    var phone = (self.data.phone || "").trim();
    if (username && username.length < 2) {
      self.setData({ errorMsg: "账号至少需要 2 个字符" });
      return;
    }
    if (username && username.length > 50) {
      self.setData({ errorMsg: "账号不能超过 50 个字符" });
      return;
    }
    if (!phone) {
      self.setData({ errorMsg: "请输入手机号" });
      return;
    }
    if (!CN_MOBILE_RE.test(phone)) {
      self.setData({ errorMsg: "请输入正确的手机号" });
      return;
    }
    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/send-code",
        method: "POST",
        data: { username: username, phone: phone },
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
          var successMsg =
            (dataObj && dataObj.message) || inner.message || resp.message || "验证码发送成功";
          var nextData = { codeCountdown: retryAfter, loading: false };
          var showDebugCode = debugCode && canShowDebugCode();
          if (showDebugCode) nextData.phoneCode = debugCode;
          self.setData(nextData);
          self._startCountdown(retryAfter);
          self._trackResetEvent("deeptutor_password_reset_code_sent");
          showSmsSentFeedback(successMsg);
          if (showDebugCode) {
            wx.showModal({
              title: "测试验证码",
              content: "当前环境未接短信服务，验证码：" + debugCode,
              showCancel: false,
            });
          }
        } else {
          self.setData({
            errorMsg: outerMsg,
            loading: false,
          });
        }
      })
      .catch(function (err) {
        var msg = self._describeAuthError(err, "发送失败，请重试", {
          customMap: describeResetAuthError,
        });
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

  handleResetPassword: function () {
    if (this.data.loading) return;
    var self = this;
    var username = (self.data.username || "").trim();
    var phone = (self.data.phone || "").trim();
    var code = (self.data.phoneCode || "").trim();
    var password = self.data.password || "";
    var confirmPassword = self.data.confirmPassword || "";
    var formError = validateResetForm(username, phone, code, password, confirmPassword);
    if (formError) {
      self.setData({ errorMsg: formError });
      return;
    }

    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/reset-password",
        method: "POST",
        data: {
          username: username,
          phone: phone,
          code: code,
          password: password,
        },
        noAuth: true,
      })
      .then(function (resp) {
        var inner = resp.data || resp;
        self._trackResetEvent("deeptutor_password_reset_success");
        wx.showModal({
          title: "密码已重置",
          content: inner.message || "请使用新密码登录鲁班智考。",
          confirmText: "去登录",
          showCancel: false,
          success: function () {
            self._goPasswordLogin();
          },
        });
      })
      .catch(function (err) {
        var msg = self._describeAuthError(err, "重置失败，请重试", {
          customMap: describeResetAuthError,
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

  _goPasswordLogin: function () {
    wx.redirectTo({
      url: route.manualLogin({
        loginMode: "password",
        username: (this.data.username || "").trim(),
        entrySource: this.data.entrySource,
        returnTo: this.data.returnTo,
      }),
    });
  },

  goBack: function () {
    var fallbackUrl = route.manualLogin({
      loginMode: "password",
      username: (this.data.username || "").trim(),
      entrySource: this.data.entrySource,
      returnTo: this.data.returnTo,
    });
    wx.navigateBack({
      fail: function () {
        wx.redirectTo({ url: fallbackUrl });
      },
    });
  },
});
