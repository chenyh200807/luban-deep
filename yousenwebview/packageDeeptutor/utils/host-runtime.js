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

module.exports = {
  getAppSafe: getAppSafe,
  getGlobalData: getGlobalData,
  getRuntimeBaseConfig: getRuntimeBaseConfig,
  rememberWorkingBaseUrl: rememberWorkingBaseUrl,
  getChatEngine: getChatEngine,
};
