var auth = require("./auth");
var route = require("./route");

var runtimeState = {
  goHomeFlag: false,
  pendingConversationId: "",
  pendingChatQuery: "",
  pendingChatMode: "AUTO",
  workspaceBackUrl: "",
  workspaceBackLabel: "",
  authRedirecting: false,
  networkAvailable: true,
  networkMonitorReady: false,
};

function _normalizeRoute(url) {
  var clean = String(url || "")
    .trim()
    .split("?")[0]
    .replace(/^\/+/, "");
  if (!clean) return "";
  if (clean.indexOf("packageDeeptutor/") === 0) return clean;
  if (clean.indexOf("pages/") === 0) return "packageDeeptutor/" + clean;
  return clean;
}

function _getCurrentRoute() {
  try {
    var pages = getCurrentPages();
    if (!pages || !pages.length) return "";
    return pages[pages.length - 1].route || "";
  } catch (_) {
    return "";
  }
}

function _reLaunch(url) {
  wx.reLaunch({
    url: url,
    complete: function () {
      runtimeState.authRedirecting = false;
    },
  });
}

function _setAuthRedirecting(flag) {
  runtimeState.authRedirecting = !!flag;
}

function _isAuthRedirecting() {
  return !!runtimeState.authRedirecting;
}

function redirectToLogin() {
  if (runtimeState.authRedirecting) return false;
  runtimeState.authRedirecting = true;
  _reLaunch(route.login());
  return true;
}

function checkAuth(callback) {
  var token = auth.getToken();
  if (!token) {
    if (_getCurrentRoute() === route.login().replace(/^\//, "")) {
      return false;
    }
    return redirectToLogin();
  }
  if (callback) callback(token);
  return true;
}

function logout() {
  auth.clearToken();
  runtimeState.goHomeFlag = false;
  runtimeState.pendingConversationId = "";
  runtimeState.pendingChatQuery = "";
  runtimeState.pendingChatMode = "AUTO";
  runtimeState.workspaceBackUrl = "";
  runtimeState.workspaceBackLabel = "";
  redirectToLogin();
}

function reLaunchTo(url) {
  _reLaunch(url);
}

function navigateTo(url) {
  wx.navigateTo({ url: url });
}

function markGoHome() {
  runtimeState.goHomeFlag = true;
}

function consumeGoHomeFlag() {
  var flag = runtimeState.goHomeFlag;
  runtimeState.goHomeFlag = false;
  return flag;
}

function setPendingConversationId(id) {
  runtimeState.pendingConversationId = id || "";
}

function consumePendingConversationId() {
  var id = runtimeState.pendingConversationId || "";
  runtimeState.pendingConversationId = "";
  return id;
}

function setPendingChatIntent(query, mode) {
  runtimeState.pendingChatQuery = query || "";
  runtimeState.pendingChatMode = mode || "AUTO";
}

function consumePendingChatIntent() {
  var query = runtimeState.pendingChatQuery || "";
  var mode = runtimeState.pendingChatMode || "AUTO";
  runtimeState.pendingChatQuery = "";
  runtimeState.pendingChatMode = "AUTO";
  return { query: query, mode: mode };
}

function setWorkspaceBack(url, label) {
  runtimeState.workspaceBackUrl = String(url || "").trim();
  runtimeState.workspaceBackLabel = String(label || "").trim();
}

function clearWorkspaceBack() {
  runtimeState.workspaceBackUrl = "";
  runtimeState.workspaceBackLabel = "";
}

function clearWorkspaceBackIfMatches(url) {
  var current = _normalizeRoute(url);
  var target = _normalizeRoute(runtimeState.workspaceBackUrl);
  if (!current || !target || current !== target) return false;
  clearWorkspaceBack();
  return true;
}

function getWorkspaceBack(currentUrl) {
  var targetUrl = String(runtimeState.workspaceBackUrl || "").trim();
  if (!targetUrl) return null;
  var current = _normalizeRoute(currentUrl || _getCurrentRoute());
  var target = _normalizeRoute(targetUrl);
  if (current && target && current === target) return null;
  return {
    url: targetUrl,
    label: runtimeState.workspaceBackLabel || "返回",
  };
}

function consumeWorkspaceBack(currentUrl) {
  var target = getWorkspaceBack(currentUrl);
  clearWorkspaceBack();
  return target;
}

function setNetworkAvailable(available) {
  runtimeState.networkAvailable = !!available;
}

function isNetworkAvailable() {
  return runtimeState.networkAvailable !== false;
}

function initNetworkMonitor() {
  if (runtimeState.networkMonitorReady) return;
  runtimeState.networkMonitorReady = true;
  try {
    wx.getNetworkType({
      success: function (res) {
        runtimeState.networkAvailable = res.networkType !== "none";
      },
    });
  } catch (_) {}
  if (typeof wx.onNetworkStatusChange === "function") {
    wx.onNetworkStatusChange(function (res) {
      runtimeState.networkAvailable = !!(res && res.isConnected);
    });
  }
}

module.exports = {
  checkAuth: checkAuth,
  logout: logout,
  redirectToLogin: redirectToLogin,
  reLaunchTo: reLaunchTo,
  navigateTo: navigateTo,
  markGoHome: markGoHome,
  consumeGoHomeFlag: consumeGoHomeFlag,
  setPendingConversationId: setPendingConversationId,
  consumePendingConversationId: consumePendingConversationId,
  setPendingChatIntent: setPendingChatIntent,
  consumePendingChatIntent: consumePendingChatIntent,
  setWorkspaceBack: setWorkspaceBack,
  getWorkspaceBack: getWorkspaceBack,
  consumeWorkspaceBack: consumeWorkspaceBack,
  clearWorkspaceBack: clearWorkspaceBack,
  clearWorkspaceBackIfMatches: clearWorkspaceBackIfMatches,
  setNetworkAvailable: setNetworkAvailable,
  isNetworkAvailable: isNetworkAvailable,
  initNetworkMonitor: initNetworkMonitor,
  isAuthRedirecting: _isAuthRedirecting,
  setAuthRedirecting: _setAuthRedirecting,
};
