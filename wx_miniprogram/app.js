// app.js — 全局应用逻辑
const auth = require("./utils/auth");
const endpoints = require("./utils/endpoints");

// [PRR-E2] Environment-aware URL switching
const _envVersion =
  (typeof __wxConfig !== "undefined" && __wxConfig.envVersion) || "release";
const _IS_DEVELOP = _envVersion === "develop";
const _IS_TRIAL = _envVersion === "trial";
const _IS_DEV = _IS_DEVELOP || _IS_TRIAL;
const _IS_DEVTOOLS =
  typeof __wxConfig !== "undefined" && __wxConfig.platform === "devtools";
// ⚠️ DEPLOY: Replace these with your real HTTPS production domains before release build
const _PROD_GATEWAY =
  (typeof __PROD_GATEWAY__ !== "undefined" && __PROD_GATEWAY__) ||
  "https://test2.yousenjiaoyu.com";
const _PROD_API =
  (typeof __PROD_API__ !== "undefined" && __PROD_API__) ||
  "https://test2.yousenjiaoyu.com";
// [PRR-CR4] Runtime guard: block startup if placeholder URLs ship to production
if (!_IS_DEV && _PROD_API.includes("example.com")) {
  console.error("[FATAL] Production URLs are still placeholder!");
  wx.showModal({
    title: "配置错误",
    content: "API 地址未配置",
    showCancel: false,
  });
}

// 真机/体验版调试: 设置公网 HTTPS 地址（通过开发者工具「编译配置」的自定义参数传入）
// 模拟器本地直连: 设置 __USE_LOCAL_DIRECT__=true，并把 __LOCAL_BASE_URL__ 指向本机后端
// 当前 DeepTutor 本地后端默认端口: http://127.0.0.1:8001
const _NGROK_URL =
  (typeof __NGROK_URL__ !== "undefined" && __NGROK_URL__) ||
  "https://test2.yousenjiaoyu.com";
const _LOCAL_BASE_URL =
  (typeof __LOCAL_BASE_URL__ !== "undefined" && __LOCAL_BASE_URL__) ||
  "http://127.0.0.1:8001";
const _LOCAL_CANDIDATES = endpoints
  .getBaseUrlCandidates(false, _LOCAL_BASE_URL)
  .filter(function (item) {
    return /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(item);
  });
const _REMOTE_FALLBACK_CANDIDATES = [_NGROK_URL].filter(function (item) {
  return (
    !!item &&
    !item.includes("example.com") &&
    /^https?:\/\//.test(item) &&
    !/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(item)
  );
});
const _HAS_REAL_NGROK =
  !!_NGROK_URL &&
  !_NGROK_URL.includes("example.com") &&
  /^https?:\/\//.test(_NGROK_URL);
const _DEFAULT_LOCAL_DIRECT = _IS_DEVELOP && _IS_DEVTOOLS;
const _USE_LOCAL_DIRECT =
  typeof __USE_LOCAL_DIRECT__ !== "undefined"
    ? !!__USE_LOCAL_DIRECT__
    : _DEFAULT_LOCAL_DIRECT;
const _USE_NGROK = _IS_DEVELOP && !_USE_LOCAL_DIRECT && _HAS_REAL_NGROK;
const _RESOLVED_GATEWAY = _USE_NGROK
  ? _NGROK_URL
  : _IS_DEVELOP
    ? _LOCAL_CANDIDATES[0] || _LOCAL_BASE_URL
    : _PROD_GATEWAY;
const _RESOLVED_API = _USE_NGROK
  ? _NGROK_URL
  : _IS_DEVELOP
    ? _LOCAL_CANDIDATES[0] || _LOCAL_BASE_URL
    : _PROD_API;
const _RUNTIME_CANDIDATES = _USE_LOCAL_DIRECT
  ? _LOCAL_CANDIDATES.slice()
  : _USE_NGROK
    ? _REMOTE_FALLBACK_CANDIDATES.slice()
    : [];

App({
  globalData: {
    token: null,
    userInfo: null,
    goHomeFlag: false,
    pendingChatQuery: "",
    pendingChatMode: "AUTO",
    gatewayUrl: _RESOLVED_GATEWAY,
    apiUrl: _RESOLVED_API,
    gatewayCandidates: _RUNTIME_CANDIDATES,
    apiCandidates: _RUNTIME_CANDIDATES,
    // 小程序聊天走 start-turn + /api/v1/ws 统一执行流。
    chatEngine: "deeptutor",
    // 主题：'dark'(默认) | 'light'
    theme: "dark",
    // [PRR-C9] Network status — pages read this to show offline hints
    networkAvailable: true,
    _authRedirecting: false,
  },

  onLaunch() {
    // WeChat Privacy Framework (base lib ≥ 2.32.3) — must register before any
    // personal-data API (phone number, profile, location) is called.
    // Backend requirement: submit 《用户隐私保护指引》 in MP admin console.
    // Capability guard: on base libs < 2.32.3 this API is absent; calling it
    // unguarded throws in onLaunch and bricks app startup for old clients.
    if (typeof wx.onNeedPrivacyAuthorization === "function") {
      wx.onNeedPrivacyAuthorization(function (resolve) {
        wx.showModal({
          title: "用户隐私保护提示",
          content:
            "在使用本小程序前，请您仔细阅读《用户隐私保护指引》，了解我们如何收集和使用您的个人信息。",
          confirmText: "同意",
          cancelText: "不同意",
          success: function (res) {
            if (res.confirm) {
              resolve({ event: "agree" });
            } else {
              resolve({ event: "disagree" });
            }
          },
        });
      });
    }

    // App 启动
    console.info(
      "[DeepTutor MP] env=%s trial=%s devtools=%s api=%s candidates=%j",
      _envVersion,
      _IS_TRIAL,
      _IS_DEVTOOLS,
      this.globalData.apiUrl,
      this.globalData.apiCandidates,
    );
    // 初始化主题
    const savedTheme = wx.getStorageSync("theme") || "dark";
    this.globalData.theme = savedTheme;

    // 检查 token 有效性
    const token = auth.getToken();
    if (token) {
      this.globalData.token = token;
      // Session 可能已过期，静默校验；fail 时清除本地凭据强制重新登录
      var that = this;
      wx.checkSession({
        fail: function () {
          // session 过期，清除本地 token 强制重新登录
          wx.removeStorageSync("token");
          wx.removeStorageSync("userInfo");
          that.globalData.token = null;
          that.globalData.userInfo = null;
        },
      });
    }

    // [PRR-C9] Network status monitoring
    wx.onNetworkStatusChange((res) => {
      this.globalData.networkAvailable = res.isConnected;
      if (!res.isConnected) {
        wx.showToast({ title: "网络已断开", icon: "none", duration: 2000 });
      } else {
        // [W5-1] Network restored — notify user and refresh current page data
        wx.showToast({ title: "网络已恢复", icon: "success", duration: 1500 });
        var pages = getCurrentPages();
        var currentPage = pages[pages.length - 1];
        if (currentPage && typeof currentPage.onNetworkRestore === "function") {
          currentPage.onNetworkRestore();
        }
      }
    });
    // Set initial state
    wx.getNetworkType({
      success: (res) => {
        this.globalData.networkAvailable = res.networkType !== "none";
      },
    });
  },

  /** 切换主题 */
  setTheme(theme) {
    this.globalData.theme = theme;
    wx.setStorageSync("theme", theme);
  },

  /** 获取当前主题 */
  getTheme() {
    return this.globalData.theme || "dark";
  },

  /** 将主题 class 应用到当前页面的 page 元素 */
  applyTheme() {
    const isLight = this.globalData.theme === "light";
    const pages = getCurrentPages();
    if (!pages.length) return;
    const currentPage = pages[pages.length - 1];
    if (currentPage && currentPage.setData) {
      currentPage.setData({ _themeClass: isLight ? "theme-light" : "" });
    }
  },

  /**
   * 校验 token 是否有效，无效则跳转登录
   * 各页面在 onShow 中调用
   */
  checkAuth(callback) {
    const token = auth.getToken();
    if (!token) {
      var pages = getCurrentPages();
      var currentRoute =
        pages && pages.length ? pages[pages.length - 1].route || "" : "";
      if (currentRoute === "pages/login/login") {
        return;
      }
      if (this.globalData._authRedirecting) {
        return;
      }
      this.globalData._authRedirecting = true;
      wx.reLaunch({
        url: "/pages/login/login",
        complete: () => {
          this.globalData._authRedirecting = false;
        },
      });
      return;
    }
    this.globalData.token = token;
    if (callback) callback(token);
  },

  /**
   * 校验手机号是否已绑定，未绑定则强制跳回登录页绑定手机。
   * 行业标准：登录后进内容页前必须有手机号。
   * 调用方式：app.ensurePhone(function() { ... });
   */
  ensurePhone(callback) {
    var self = this;
    var pages = getCurrentPages();
    var currentRoute =
      pages && pages.length ? pages[pages.length - 1].route || "" : "";
    if (currentRoute === "pages/login/login") {
      if (callback) callback();
      return;
    }
    // 复用 globalData 里已缓存的 userInfo，避免重复请求
    var cached = self.globalData.userInfo;
    if (cached && cached._phoneChecked) {
      if (callback) callback();
      return;
    }
    var api = require("./utils/api");
    api
      .getUserInfo()
      .then(function (raw) {
        var info = api.unwrapResponse
          ? api.unwrapResponse(raw)
          : raw.data || raw;
        var phone = ((info && info.phone) || "").trim().replace(/\D/g, "");
        if (!phone || phone.length < 8) {
          // 没有手机号 → 强制跳回登录页绑定
          if (self.globalData._authRedirecting) return;
          self.globalData._authRedirecting = true;
          wx.reLaunch({
            url: "/pages/login/login",
            complete: function () {
              self.globalData._authRedirecting = false;
            },
          });
          return;
        }
        // 有手机号 → 缓存结果，执行回调
        self.globalData.userInfo = Object.assign({}, info, {
          _phoneChecked: true,
        });
        if (callback) callback();
      })
      .catch(function () {
        // getUserInfo 失败（如 401）—— api.js 会自动跳登录，不调 callback
        // 避免网络失败时放行无手机用户进入聊天
      });
  },

  /**
   * 退出登录
   */
  logout() {
    auth.clearToken();
    this.globalData.token = null;
    this.globalData.userInfo = null;
    if (this.globalData._authRedirecting) return;
    this.globalData._authRedirecting = true;
    wx.reLaunch({
      url: "/pages/login/login",
      complete: () => {
        this.globalData._authRedirecting = false;
      },
    });
  },
});
