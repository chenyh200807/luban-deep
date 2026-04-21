var auth = require("./auth");
var route = require("./route");

var fallbackRuntimeState = {
  goHomeFlag: false,
  pendingConversationId: "",
  pendingChatQuery: "",
  pendingChatMode: "AUTO",
  _authRedirecting: false,
  networkAvailable: true,
};
var workspaceBackState = {
  url: "",
  label: "",
};
var networkMonitorReady = false;

function getAppSafe() {
  try {
    return typeof getApp === "function" ? getApp() : null;
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

function getRuntimeStore() {
  return getGlobalData() || fallbackRuntimeState;
}

function resetSessionState() {
  var store = getRuntimeStore();
  store.goHomeFlag = false;
  store.pendingConversationId = "";
  store.pendingChatQuery = "";
  store.pendingChatMode = "AUTO";
  store._authRedirecting = false;
}

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
      getRuntimeStore()._authRedirecting = false;
    },
  });
}

function _setAuthRedirecting(flag) {
  getRuntimeStore()._authRedirecting = !!flag;
}

function _isAuthRedirecting() {
  return !!getRuntimeStore()._authRedirecting;
}

function redirectToLogin() {
  var store = getRuntimeStore();
  if (store._authRedirecting) return false;
  store._authRedirecting = true;
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
  resetSessionState();
  redirectToLogin();
}

function reLaunchTo(url) {
  _reLaunch(url);
}

function navigateTo(url) {
  wx.navigateTo({ url: url });
}

function markGoHome() {
  getRuntimeStore().goHomeFlag = true;
}

function consumeGoHomeFlag() {
  var store = getRuntimeStore();
  var flag = !!store.goHomeFlag;
  store.goHomeFlag = false;
  return flag;
}

function setPendingConversationId(id) {
  getRuntimeStore().pendingConversationId = id || "";
}

function consumePendingConversationId() {
  var store = getRuntimeStore();
  var id = store.pendingConversationId || "";
  store.pendingConversationId = "";
  return id;
}

function setPendingChatIntent(query, mode) {
  var store = getRuntimeStore();
  store.pendingChatQuery = query || "";
  store.pendingChatMode = mode || "AUTO";
}

function consumePendingChatIntent() {
  var store = getRuntimeStore();
  var query = store.pendingChatQuery || "";
  var mode = store.pendingChatMode || "AUTO";
  store.pendingChatQuery = "";
  store.pendingChatMode = "AUTO";
  return { query: query, mode: mode };
}

function setWorkspaceBack(url, label) {
  workspaceBackState.url = String(url || "").trim();
  workspaceBackState.label = String(label || "").trim();
}

function clearWorkspaceBack() {
  workspaceBackState.url = "";
  workspaceBackState.label = "";
}

function clearWorkspaceBackIfMatches(url) {
  var current = _normalizeRoute(url);
  var target = _normalizeRoute(workspaceBackState.url);
  if (!current || !target || current !== target) return false;
  clearWorkspaceBack();
  return true;
}

function getWorkspaceBack(currentUrl) {
  var targetUrl = String(workspaceBackState.url || "").trim();
  if (!targetUrl) return null;
  var current = _normalizeRoute(currentUrl || _getCurrentRoute());
  var target = _normalizeRoute(targetUrl);
  if (current && target && current === target) return null;
  return {
    url: targetUrl,
    label: workspaceBackState.label || "返回",
  };
}

function consumeWorkspaceBack(currentUrl) {
  var target = getWorkspaceBack(currentUrl);
  clearWorkspaceBack();
  return target;
}

function setNetworkAvailable(available) {
  getRuntimeStore().networkAvailable = !!available;
}

function isNetworkAvailable() {
  return getRuntimeStore().networkAvailable !== false;
}

function initNetworkMonitor() {
  if (networkMonitorReady) return;
  networkMonitorReady = true;
  try {
    wx.getNetworkType({
      success: function (res) {
        getRuntimeStore().networkAvailable = res.networkType !== "none";
      },
    });
  } catch (_) {}
  if (typeof wx.onNetworkStatusChange === "function") {
    wx.onNetworkStatusChange(function (res) {
      getRuntimeStore().networkAvailable = !!(res && res.isConnected);
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
