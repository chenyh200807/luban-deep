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
const _HAS_REAL_NGROK =
  !!_NGROK_URL && !_NGROK_URL.includes("example.com") && /^https?:\/\//.test(_NGROK_URL);
const _USE_LOCAL_DIRECT =
  typeof __USE_LOCAL_DIRECT__ !== "undefined"
    ? !!__USE_LOCAL_DIRECT__
    : _IS_DEVTOOLS && _IS_DEVELOP;
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
const _RUNTIME_CANDIDATES =
  _USE_NGROK || _IS_DEVELOP ? _LOCAL_CANDIDATES.slice() : [];

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
    // App 启动
    console.info("[DeepTutor MP] env=%s trial=%s devtools=%s api=%s candidates=%j",
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
