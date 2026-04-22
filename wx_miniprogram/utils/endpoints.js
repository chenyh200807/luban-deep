// utils/endpoints.js — 小程序 API 地址解析与回退

var DEFAULT_REMOTE_BASES = ["https://test2.yousenjiaoyu.com"];
var DEFAULT_LOCAL_BASES = ["http://127.0.0.1:8001", "http://127.0.0.1:8012"];
var ENV_VERSION =
  (typeof __wxConfig !== "undefined" && __wxConfig.envVersion) || "release";
var IS_DEVELOP = ENV_VERSION === "develop";

function getAppSafe() {
  try {
    return getApp();
  } catch (_) {
    return null;
  }
}

function getRuntimeBaseConfig(useGateway) {
  var app = getAppSafe();
  if (!app || !app.globalData || typeof app.globalData !== "object") {
    return { primary: "", candidates: [] };
  }
  var primary = useGateway ? app.globalData.gatewayUrl : app.globalData.apiUrl;
  var candidates = useGateway
    ? app.globalData.gatewayCandidates || []
    : app.globalData.apiCandidates || [];
  return {
    primary: String(primary || "").trim(),
    candidates: Array.isArray(candidates) ? candidates.slice() : [],
  };
}

function rememberRuntimeBaseUrl(baseUrl, useGateway) {
  var app = getAppSafe();
  var normalized = String(baseUrl || "").trim();
  if (!app || !app.globalData || !normalized) return;
  if (useGateway) {
    app.globalData.gatewayUrl = normalized;
  } else {
    app.globalData.apiUrl = normalized;
  }
}

function uniq(list) {
  var seen = {};
  var out = [];
  for (var i = 0; i < list.length; i++) {
    var item = String(list[i] || "").trim();
    if (!item || seen[item]) continue;
    seen[item] = true;
    out.push(item);
  }
  return out;
}

function isLocalBase(url) {
  return /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(
    String(url || "").trim(),
  );
}

function getConfiguredBases(useGateway) {
  var config = getRuntimeBaseConfig(!!useGateway);
  if (config.primary || config.candidates.length) {
    return uniq([config.primary].concat(config.candidates || []));
  }
  if (IS_DEVELOP) {
    return uniq(DEFAULT_LOCAL_BASES.concat(DEFAULT_REMOTE_BASES));
  }
  return DEFAULT_REMOTE_BASES.slice();
}

function getBaseUrlCandidates(useGateway, preferredBase) {
  var list = [];
  if (preferredBase) list.push(preferredBase);
  list = list.concat(getConfiguredBases(!!useGateway));
  return uniq(list);
}

function getPrimaryBaseUrl(useGateway) {
  var candidates = getBaseUrlCandidates(!!useGateway);
  return candidates[0] || (IS_DEVELOP ? DEFAULT_LOCAL_BASES[0] : DEFAULT_REMOTE_BASES[0]);
}

function rememberWorkingBaseUrl(baseUrl, useGateway) {
  rememberRuntimeBaseUrl(baseUrl, !!useGateway);
}

function toSocketBaseUrl(baseUrl) {
  var normalized = String(baseUrl || "").trim();
  if (!normalized) return "";
  if (normalized.indexOf("https://") === 0) {
    return "wss://" + normalized.slice("https://".length);
  }
  if (normalized.indexOf("http://") === 0) {
    return "ws://" + normalized.slice("http://".length);
  }
  if (normalized.indexOf("wss://") === 0 || normalized.indexOf("ws://") === 0) {
    return normalized;
  }
  return normalized;
}

function getSocketUrlCandidates(path, preferredBase) {
  var normalizedPath = String(path || "/api/v1/ws").trim() || "/api/v1/ws";
  var bases = getBaseUrlCandidates(false, preferredBase);
  var urls = [];
  for (var i = 0; i < bases.length; i++) {
    var socketBase = toSocketBaseUrl(bases[i]);
    if (!socketBase) continue;
    urls.push(socketBase + normalizedPath);
  }
  return uniq(urls);
}

module.exports = {
  DEFAULT_REMOTE_BASES: DEFAULT_REMOTE_BASES,
  DEFAULT_LOCAL_BASES: DEFAULT_LOCAL_BASES,
  getBaseUrlCandidates: getBaseUrlCandidates,
  getPrimaryBaseUrl: getPrimaryBaseUrl,
  rememberWorkingBaseUrl: rememberWorkingBaseUrl,
  toSocketBaseUrl: toSocketBaseUrl,
  getSocketUrlCandidates: getSocketUrlCandidates,
};
