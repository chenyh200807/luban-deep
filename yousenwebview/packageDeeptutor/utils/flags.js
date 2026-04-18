var route = require("./route");
var hostRuntime = require("./host-runtime");
var runtime = require("./runtime");

var DEFAULT_FLAGS = {
  workspaceEnabled: true,
  historyEnabled: true,
  reportEnabled: true,
  profileEnabled: true,
  assessmentEnabled: true,
};

var FEATURE_META = {
  history: {
    key: "historyEnabled",
    label: "历史",
    fallbackUrl: route.chat(),
    pageUrl: route.history(),
  },
  report: {
    key: "reportEnabled",
    label: "学情",
    fallbackUrl: route.chat(),
    pageUrl: route.report(),
  },
  profile: {
    key: "profileEnabled",
    label: "我的",
    fallbackUrl: route.chat(),
    pageUrl: route.profile(),
  },
  assessment: {
    key: "assessmentEnabled",
    label: "摸底测试",
    fallbackUrl: route.chat(),
    pageUrl: route.assessment(),
  },
};

function normalizeRoutePath(url) {
  var raw = String(url || "").trim();
  if (!raw) return "";
  var clean = raw.split("?")[0];
  if (!clean) return "";
  if (clean.indexOf("/packageDeeptutor/") === 0) return clean;
  if (clean.indexOf("packageDeeptutor/") === 0) return "/" + clean;
  if (clean.indexOf("/pages/") === 0) return route.resolve(clean.slice(1));
  if (clean.indexOf("pages/") === 0) return route.resolve(clean);
  return clean;
}

function getWorkspaceFlags() {
  var runtimeFlags = hostRuntime.getWorkspaceFlags();
  if (runtimeFlags && typeof runtimeFlags === "object") {
    return Object.assign({}, DEFAULT_FLAGS, runtimeFlags);
  }
  return Object.assign({}, DEFAULT_FLAGS);
}

function isWorkspaceEnabled() {
  return getWorkspaceFlags().workspaceEnabled !== false;
}

function isFeatureEnabled(name) {
  var meta = FEATURE_META[name];
  if (!meta) return true;
  var flags = getWorkspaceFlags();
  if (flags.workspaceEnabled === false && name !== "assessment") {
    return false;
  }
  return flags[meta.key] !== false;
}

function shouldShowWorkspaceShell() {
  if (!isWorkspaceEnabled()) return false;
  return (
    isFeatureEnabled("history") ||
    isFeatureEnabled("report") ||
    isFeatureEnabled("profile")
  );
}

function getFeatureByRoute(url) {
  var normalized = normalizeRoutePath(url);
  if (!normalized) return "";
  var names = Object.keys(FEATURE_META);
  for (var i = 0; i < names.length; i++) {
    var name = names[i];
    if (normalizeRoutePath(FEATURE_META[name].pageUrl) === normalized) {
      return name;
    }
  }
  return "";
}

function isRouteEnabled(url) {
  var feature = getFeatureByRoute(url);
  if (!feature) return true;
  return isFeatureEnabled(feature);
}

function resolveShellList(baseList) {
  var list = Array.isArray(baseList) ? baseList.slice() : [];
  return list.map(function (item) {
    var next = Object.assign({}, item);
    if (next.pagePath === route.history()) {
      next.hidden = !isFeatureEnabled("history");
    } else if (next.pagePath === route.report()) {
      next.hidden = !isFeatureEnabled("report");
    } else if (next.pagePath === route.profile()) {
      next.hidden = !isFeatureEnabled("profile");
    } else {
      next.hidden = false;
    }
    return next;
  });
}

function ensureFeatureEnabled(name, options) {
  if (isFeatureEnabled(name)) return true;
  var meta = FEATURE_META[name] || {};
  if (meta.pageUrl) {
    runtime.clearWorkspaceBackIfMatches(meta.pageUrl);
  }
  var config = options && typeof options === "object" ? options : {};
  var message = config.message || (meta.label ? meta.label + "暂未开放" : "当前功能暂未开放");
  wx.showToast({ title: message, icon: "none" });
  if (config.redirect === false) return false;
  var fallbackUrl = config.fallbackUrl || meta.fallbackUrl;
  if (fallbackUrl) {
    wx.reLaunch({ url: fallbackUrl });
  }
  return false;
}

module.exports = {
  getWorkspaceFlags: getWorkspaceFlags,
  isWorkspaceEnabled: isWorkspaceEnabled,
  isFeatureEnabled: isFeatureEnabled,
  shouldShowWorkspaceShell: shouldShowWorkspaceShell,
  getFeatureByRoute: getFeatureByRoute,
  isRouteEnabled: isRouteEnabled,
  resolveShellList: resolveShellList,
  ensureFeatureEnabled: ensureFeatureEnabled,
};
