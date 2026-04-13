// utils/endpoints.js — 小程序 API 地址解析与回退

var DEFAULT_LOCAL_BASES = ["http://127.0.0.1:8001", "http://127.0.0.1:8012"];

function getAppSafe() {
  try {
    return getApp();
  } catch (e) {
    return null;
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
  var app = getAppSafe();
  if (!app || !app.globalData) return [];
  var primary = useGateway ? app.globalData.gatewayUrl : app.globalData.apiUrl;
  var extras = useGateway
    ? app.globalData.gatewayCandidates || []
    : app.globalData.apiCandidates || [];
  var list = [primary];
  if (Array.isArray(extras)) list = list.concat(extras);
  if (isLocalBase(primary)) list = list.concat(DEFAULT_LOCAL_BASES);
  return uniq(list);
}

function getBaseUrlCandidates(useGateway, preferredBase) {
  var list = [];
  if (preferredBase) list.push(preferredBase);
  list = list.concat(getConfiguredBases(!!useGateway));
  list = list.concat(DEFAULT_LOCAL_BASES);
  return uniq(list);
}

function getPrimaryBaseUrl(useGateway) {
  var candidates = getBaseUrlCandidates(!!useGateway);
  return candidates[0] || DEFAULT_LOCAL_BASES[0];
}

function rememberWorkingBaseUrl(baseUrl, useGateway) {
  var app = getAppSafe();
  if (!app || !app.globalData || !baseUrl) return;
  if (useGateway) {
    app.globalData.gatewayUrl = baseUrl;
  } else {
    app.globalData.apiUrl = baseUrl;
  }
}

module.exports = {
  DEFAULT_LOCAL_BASES: DEFAULT_LOCAL_BASES,
  getBaseUrlCandidates: getBaseUrlCandidates,
  getPrimaryBaseUrl: getPrimaryBaseUrl,
  rememberWorkingBaseUrl: rememberWorkingBaseUrl,
};
