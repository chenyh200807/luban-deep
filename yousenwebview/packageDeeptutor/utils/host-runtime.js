function getAppSafe() {
  try {
    return getApp();
  } catch (_) {
    return null;
  }
}

function getGlobalData() {
  var app = getAppSafe();
  if (!app || !app.globalData || typeof app.globalData !== "object") {
    return null;
  }
  return app.globalData;
}

function getRuntimeBaseConfig(useGateway) {
  var globalData = getGlobalData();
  if (!globalData) {
    return { primary: "", candidates: [] };
  }
  var primary = useGateway ? globalData.gatewayUrl : globalData.apiUrl;
  var candidates = useGateway
    ? globalData.gatewayCandidates || []
    : globalData.apiCandidates || [];
  return {
    primary: String(primary || "").trim(),
    candidates: Array.isArray(candidates) ? candidates.slice() : [],
  };
}

function rememberWorkingBaseUrl(baseUrl, useGateway) {
  var globalData = getGlobalData();
  var normalized = String(baseUrl || "").trim();
  if (!globalData || !normalized) return;
  if (useGateway) {
    globalData.gatewayUrl = normalized;
  } else {
    globalData.apiUrl = normalized;
  }
}

function getChatEngine() {
  var globalData = getGlobalData();
  if (!globalData) return "";
  return String(globalData.chatEngine || "").trim();
}

function getTheme() {
  // 主题单一权威(2026-07-18):未显式选择=亮;旧默认暗是 tab 壳与页面
  // 明暗打架的根源,禁止回潮。
  return getThemeOr("light");
}

/** 读主题；用户从未显式选择时返回 fallback（页面级默认亮/暗由调用方决定）。 */
function getThemeOr(fallback) {
  var fb = String(fallback || "dark").trim() || "dark";
  var globalData = getGlobalData();
  if (globalData && globalData.theme) {
    return String(globalData.theme || "").trim() || fb;
  }
  try {
    return wx.getStorageSync("theme") || fb;
  } catch (_) {
    return fb;
  }
}

function setTheme(theme) {
  var normalized = String(theme || "").trim() || "dark";
  try {
    wx.setStorageSync("theme", normalized);
  } catch (_) {}
  var globalData = getGlobalData();
  if (globalData) {
    globalData.theme = normalized;
  }
  return normalized;
}

function getWorkspaceFlags() {
  var app = getAppSafe();
  if (app && typeof app.getDeeptutorWorkspaceFlags === "function") {
    try {
      return app.getDeeptutorWorkspaceFlags();
    } catch (_) {}
  }
  var globalData = getGlobalData();
  if (globalData && globalData.deeptutorWorkspaceFlags) {
    return Object.assign({}, globalData.deeptutorWorkspaceFlags);
  }
  return null;
}

module.exports = {
  getAppSafe: getAppSafe,
  getGlobalData: getGlobalData,
  getRuntimeBaseConfig: getRuntimeBaseConfig,
  rememberWorkingBaseUrl: rememberWorkingBaseUrl,
  getChatEngine: getChatEngine,
  getTheme: getTheme,
  getThemeOr: getThemeOr,
  setTheme: setTheme,
  getWorkspaceFlags: getWorkspaceFlags,
};
