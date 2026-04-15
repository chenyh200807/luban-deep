var route = require("./route");

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
  },
  report: {
    key: "reportEnabled",
    label: "学情",
    fallbackUrl: route.chat(),
  },
  profile: {
    key: "profileEnabled",
    label: "我的",
    fallbackUrl: route.chat(),
  },
  assessment: {
    key: "assessmentEnabled",
    label: "摸底测试",
    fallbackUrl: route.chat(),
  },
};

function getWorkspaceFlags() {
  try {
    var app = getApp();
    if (app && typeof app.getDeeptutorWorkspaceFlags === "function") {
      return app.getDeeptutorWorkspaceFlags();
    }
  } catch (_) {}
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
  resolveShellList: resolveShellList,
  ensureFeatureEnabled: ensureFeatureEnabled,
};
