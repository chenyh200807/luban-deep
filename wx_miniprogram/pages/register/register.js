var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");
var firstRunEntry = require("../../utils/first-run-entry");

var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
var CN_MOBILE_RE = /^1[3-9]\d{9}$/;
var REGISTER_NOTICE_ITEMS = [
  "本服务为 AI 备考辅助工具，练习、讲解、批改、估分、学情分析和学习建议仅供参考，不承诺通过考试、提升特定分数、达到特定排名或取得任何资格结果。",
  "AI 批改、采分点诊断、错因分析和模拟评分不等同于考试机构、阅卷老师或官方评分标准的最终认定；涉及教材、规范、政策、考试大纲和真题解析的内容，应以最新官方发布为准。",
  "你应自行核验本服务输出内容，并对据此作出的学习安排、资料选择、报考决策、工程实践判断或对外传播行为承担相应后果。",
  "你上传、输入或传播的题目、图片、讲义、笔记、答案及其他内容，应保证来源合法，不侵犯第三方权益，不包含违法、泄密或不当信息；由此引发的投诉或责任由你依法承担。",
  "你应提供真实、准确、有效的手机号、微信授权信息和账号资料，妥善保管登录凭证；未成年人注册或使用本服务，应事先取得监护人同意并在其指导下使用。",
  "因微信、支付渠道、云服务、模型服务、网络运营商、终端设备或第三方接口原因造成的服务延迟、中断、错误或数据同步异常，平台将在合理范围内协助处理，但不承担超出法律规定和平台过错范围的责任。",
  "因自然灾害、政策监管、网络攻击、系统安全事件、基础设施故障等不可抗力或不可归责于平台的原因导致服务异常，平台可采取暂停、限流、修复、回滚等必要措施。",
  "除法律另有强制规定、平台故意或重大过失外，平台因本服务承担的赔偿责任以你就相关争议服务实际支付的费用为合理上限；本说明不排除或限制你依法享有的消费者权益。",
];

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
  if (
    !/[A-Z]/.test(password) ||
    !/[a-z]/.test(password) ||
    !/\d/.test(password)
  ) {
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
    registerNoticeItems: REGISTER_NOTICE_ITEMS,
  },
  onLoad: function () {
    this._mounted = true;
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
      // 已登录=返回用户，直达 chat，不进首跑剧本
      firstRunEntry.goHomeAfterAuth(false);
      return;
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
    var formError = validateRegisterForm(
      username,
      phone,
      password,
      confirmPassword,
    );

    if (formError) {
      self.setData({ errorMsg: formError });
      return;
    }

    self.setData({ loading: true, errorMsg: "" });
    var attribution = api.regAttribution();
    api
      .request({
        url: "/api/v1/auth/register",
        method: "POST",
        data: {
          username: username,
          password: password,
          phone: phone,
          channel: attribution.channel,
          scene: attribution.scene,
        },
        noAuth: true,
      })
      .then(function (resp) {
        if (!self._mounted) return;
        var inner = resp.data || resp;
        var user = inner.user || resp.user || {};
        var token =
          inner.token ||
          inner._token ||
          resp.token ||
          resp._token ||
          user._token;
        if (!token) throw new Error("服务端未返回凭证");
        auth.setToken(token, inner.expires_at, inner);
        firstRunEntry.goHomeAfterAuth(true);
      })
      .catch(function (err) {
        if (!self._mounted) return;
        var m = String((err && err.message) || "");
        var msg = "注册失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("429")) msg = "注册过于频繁，请稍后再试";
        else if (m && !m.startsWith("HTTP_")) msg = m;
        self.setData({ errorMsg: msg });
      })
      .then(
        function () {
          if (!self._mounted) return;
          self.setData({ loading: false });
        },
        function () {
          if (!self._mounted) return;
          self.setData({ loading: false });
        },
      );
  },
  onUnload: function () {
    this._mounted = false;
  },
  goLogin: function () {
    wx.navigateBack({
      fail: function () {
        wx.redirectTo({ url: "/pages/login/login" });
      },
    });
  },
  openTerms: function () {
    wx.navigateTo({ url: "/pages/legal/terms" });
  },
  _completeWechatAuth: function (payload) {
    var inner = payload && (payload.data || payload);
    var token = inner && inner.token;
    if (!token) throw new Error("服务端未返回凭证");
    auth.setToken(token, inner.expires_at, inner);
  },
  handleWechatRegister: function () {
    if (this.data.wechatLoading || this.data.loading) return;
    this.setData({ errorMsg: "请先完成手机号验证" });
  },
  handleWechatPhoneNumber: function (e) {
    var self = this;
    if (self.data.wechatLoading || self.data.loading) return;
    var phoneCode =
      e && e.detail && (e.detail.code || e.detail.phoneCode || "");
    if (!phoneCode) {
      self.setData({ errorMsg: "未完成手机号验证" });
      return;
    }
    self.setData({ wechatLoading: true, errorMsg: "" });
    wx.login({
      success: function (loginRes) {
        if (!self._mounted) return;
        if (!loginRes.code) {
          self.setData({
            wechatLoading: false,
            errorMsg: "快捷注册失败，请重试",
          });
          return;
        }
        api
          .wxLoginWithPhone(loginRes.code, phoneCode)
          .then(function (resp) {
            if (!self._mounted) return;
            self._completeWechatAuth(resp);
            firstRunEntry.goHomeAfterAuth(true);
          })
          .catch(function (err) {
            if (!self._mounted) return;
            var m = String((err && err.message) || "");
            var msg = "快捷注册失败，请重试";
            if (m.includes("credentials")) msg = "后端未配置小程序密钥";
            else if (m.includes("getuserphonenumber")) msg = "手机号验证失败";
            else if (m.includes("NETWORK_")) msg = "网络连接失败";
            else if (m && !m.startsWith("HTTP_")) msg = m;
            self.setData({ errorMsg: msg });
          })
          .then(
            function () {
              if (!self._mounted) return;
              self.setData({ wechatLoading: false });
            },
            function () {
              if (!self._mounted) return;
              self.setData({ wechatLoading: false });
            },
          );
      },
      fail: function () {
        if (!self._mounted) return;
        self.setData({ wechatLoading: false, errorMsg: "无法获取登录凭证" });
      },
    });
  },
});
