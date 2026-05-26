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
  var globalData = getGlobalData();
  if (globalData && globalData.theme) {
    return String(globalData.theme || "").trim() || "dark";
  }
  try {
    return wx.getStorageSync("theme") || "dark";
  } catch (_) {
    return "dark";
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
  setTheme: setTheme,
  getWorkspaceFlags: getWorkspaceFlags,
};
