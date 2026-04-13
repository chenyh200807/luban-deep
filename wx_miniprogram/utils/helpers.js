// utils/helpers.js — 共享工具函数（消除页面间重复代码）

/**
 * 友好时间格式化
 * @param {string} isoStr - ISO 时间字符串
 * @returns {string}
 */
function formatTime(isoStr) {
  if (!isoStr) return "";
  try {
    var d = new Date(isoStr);
    if (isNaN(d.getTime())) return "";
    var now = new Date();
    var diff = now - d;
    if (diff < 60000) return "刚刚";
    if (diff < 3600000) return Math.floor(diff / 60000) + " 分钟前";
    if (diff < 86400000) return Math.floor(diff / 3600000) + " 小时前";
    var pad = function (n) {
      return n < 10 ? "0" + n : "" + n;
    };
    return (
      d.getMonth() +
      1 +
      "/" +
      d.getDate() +
      " " +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes())
    );
  } catch (_) {
    return "";
  }
}

/**
 * 获取时间问候语
 * @returns {string}
 */
function getTimeGreeting() {
  var h = new Date().getHours();
  if (h < 6) return "凌晨好";
  if (h < 12) return "上午好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

/**
 * 获取当前主题（统一入口，单一数据源）
 * 优先级：App.globalData.theme > Storage > 默认 "dark"
 * @returns {string} "dark" | "light"
 */
function getTheme() {
  try {
    var app = getApp();
    if (app && app.globalData && app.globalData.theme) {
      return app.globalData.theme;
    }
  } catch (_) {}
  return wx.getStorageSync("theme") || "dark";
}

/**
 * 设置主题（统一写入入口，同步 globalData + Storage）
 * @param {string} theme - "dark" | "light"
 */
function setTheme(theme) {
  wx.setStorageSync("theme", theme);
  try {
    var app = getApp();
    if (app && app.globalData) {
      app.globalData.theme = theme;
    }
  } catch (_) {}
}

/**
 * 判断是否深色模式
 * @returns {boolean}
 */
function isDark() {
  return getTheme() !== "light";
}

/**
 * 同步 TabBar 主题和选中状态
 * @param {object} page - 页面实例
 * @param {number} selected - TabBar 选中索引
 * @param {object} [extra] - 额外 setData 参数
 */
function syncTabBar(page, selected, extra) {
  if (typeof page.getTabBar === "function" && page.getTabBar()) {
    var data = { selected: selected, isDark: isDark() };
    if (extra) {
      Object.keys(extra).forEach(function (k) {
        data[k] = extra[k];
      });
    }
    page.getTabBar().setData(data);
  }
}

/**
 * 安全振动 — 兼容不支持 type 参数的旧系统（iOS 13.0-13.3）
 * @param {string} [type] - "light" | "medium" | "heavy"
 */
function vibrate(type) {
  try {
    wx.vibrateShort({
      type: type || "light",
      fail: function () {
        /* 静默失败 */
      },
    });
  } catch (_) {
    // 极端老旧设备完全不支持振动 API
  }
}

/**
 * 获取窗口信息 — 兼容新旧 API
 * wx.getWindowInfo (2.16.0+) > wx.getSystemInfoSync (旧版)
 * @returns {object}
 */
function getWindowInfo() {
  if (wx.getWindowInfo) {
    return wx.getWindowInfo();
  }
  // 降级到旧 API
  try {
    var sys = wx.getSystemInfoSync();
    return {
      statusBarHeight: sys.statusBarHeight || 44,
      screenHeight: sys.screenHeight || 812,
      screenWidth: sys.screenWidth || 375,
      windowHeight: sys.windowHeight || 812,
      windowWidth: sys.windowWidth || 375,
      safeArea: sys.safeArea || { bottom: sys.screenHeight || 812 },
    };
  } catch (_) {
    return {
      statusBarHeight: 44,
      screenHeight: 812,
      screenWidth: 375,
      windowHeight: 812,
      windowWidth: 375,
      safeArea: { bottom: 812 },
    };
  }
}

// ── 性能分级系统 ──────────────────────────────────────────

/**
 * 设备性能等级（缓存结果，只检测一次）
 *   "high"   — 旗舰机 (iPhone 11+, 骁龙 8xx, 6GB+)
 *   "medium" — 中端机 (iPhone 8-X, 骁龙 7xx, 4-6GB)
 *   "low"    — 低端机 (iPhone 6s-7, 骁龙 4xx/6xx, 2-3GB, Android ≤8)
 *
 * 检测依据: wx.getDeviceInfo().benchmarkLevel (微信官方性能评分)
 *           + 内存 + 系统版本 综合判定
 */
var _perfLevel = null;

function getPerformanceLevel() {
  if (_perfLevel) return _perfLevel;

  var level = "high"; // 默认高端
  try {
    var sys = wx.getSystemInfoSync();

    // 1) 微信官方 benchmarkLevel（-1=未知, >=0 数值越高越好）
    //    iOS 无此字段; Android: 0-10 低端, 10-20 中端, 20+ 高端
    var bench = sys.benchmarkLevel;
    if (typeof bench === "number" && bench >= 0) {
      if (bench < 10) level = "low";
      else if (bench < 20) level = "medium";
      else level = "high";
    }

    // 2) 内存辅助判定（安卓有效，iOS 不返回此字段）
    //    deviceMemory 以 GB 为单位（部分微信版本为 MB）
    var mem = sys.memorySize || 0; // MB
    if (mem > 0 && mem <= 3072) {
      level = "low";
    } else if (mem > 3072 && mem <= 5120 && level === "high") {
      level = "medium";
    }

    // 3) 系统版本兜底
    var platform = (sys.platform || "").toLowerCase();
    var sysVersion =
      parseFloat(sys.system && sys.system.replace(/[^0-9.]/g, "")) || 0;

    if (platform === "android" && sysVersion > 0 && sysVersion <= 8) {
      level = "low";
    }
    // iPhone 6s/7/8 运行 iOS 13-14 → 中端
    if (platform === "ios" && sysVersion >= 13 && sysVersion < 15) {
      if (level === "high") level = "medium";
    }
  } catch (_) {
    level = "medium"; // 检测失败保守处理
  }

  _perfLevel = level;
  return level;
}

/**
 * 是否低端设备
 */
function isLowEnd() {
  return getPerformanceLevel() === "low";
}

/**
 * 获取动效配置 — 不同设备等级返回不同参数
 * @returns {object}
 */
function getAnimConfig() {
  var level = getPerformanceLevel();
  if (level === "low") {
    return {
      enableBreathingOrbs: true, // 3球物理轻量，低端也开启
      enableMarquee: true, // 保留首页横向跑马灯
      enableMsgAnimation: false, // 关闭消息入场动画
      enableFocusPulse: false, // 关闭焦点脉冲
      orbIntervalMs: 80, // 低端降帧但不关闭
      subtitleIntervalMs: 5000, // 字幕轮播减速
      flushThrottleMs: 200, // 流式刷新降频
      mdParseInterval: 5, // 每 5 次才解析一次 Markdown
    };
  }
  if (level === "medium") {
    return {
      enableBreathingOrbs: true,
      enableMarquee: true,
      enableMsgAnimation: true,
      enableFocusPulse: true,
      orbIntervalMs: 60, // 与 high 一致，中端机跑 3 球无压力
      subtitleIntervalMs: 3200,
      flushThrottleMs: 120,
      mdParseInterval: 3,
    };
  }
  // high
  return {
    enableBreathingOrbs: true,
    enableMarquee: true,
    enableMsgAnimation: true,
    enableFocusPulse: true,
    orbIntervalMs: 60, // 全速物理引擎
    subtitleIntervalMs: 3200,
    flushThrottleMs: 100,
    mdParseInterval: 3,
  };
}

module.exports = {
  formatTime: formatTime,
  getTimeGreeting: getTimeGreeting,
  getTheme: getTheme,
  setTheme: setTheme,
  isDark: isDark,
  syncTabBar: syncTabBar,
  vibrate: vibrate,
  getWindowInfo: getWindowInfo,
  getPerformanceLevel: getPerformanceLevel,
  isLowEnd: isLowEnd,
  getAnimConfig: getAnimConfig,
};
