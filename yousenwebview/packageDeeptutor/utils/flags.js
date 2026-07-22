var route = require("./route");
var hostRuntime = require("./host-runtime");
var runtime = require("./runtime");

var DEFAULT_FLAGS = {
  workspaceEnabled: true,
  historyEnabled: true,
  reportEnabled: true,
  profileEnabled: true,
  assessmentEnabled: true,
  // Task C 入口收权(双轮 spike):登录后是否落"学习双轮"而非"问鲁班(chat)"。
  // 护栏1=默认关:关时 host 落地行为逐字节不变(仅 spike cohort 由 host 运行时 flag 开)。
  doubleWheelLandingEnabled: false,
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

// Task C 入口收权(护栏1):登录后是否落双轮学习页。严格 === true(默认关 = host 不变)。
function shouldLandOnDoubleWheel() {
  return getWorkspaceFlags().doubleWheelLandingEnabled === true;
}

// 教学视频可开放集数上限(纯函数,便于单测)。serverLimit = 服务端
// GET /api/v1/billing/wallet 下发的 teaching_video_limit(前端不自算,只消费)。
// 服务端明确 null = 无限；非负整数 = 上限；缺失/失败/非法 = 0（fail closed）。
function resolveTeachingVideoLimit(serverLimit) {
  if (serverLimit === null) return null;
  if (typeof serverLimit === "number" && isFinite(serverLimit) && serverLimit >= 0) {
    return Math.floor(serverLimit);
  }
  return 0;
}

// Task C 登录后落地目标决策(单一权威纯函数,便于测试):
// - flag 关 → 原样返回 target(host 逐字节不变);
// - flag 开且目标是问鲁班(chat)→ 翻到 learnUrl(护栏2:仅翻 chat→learn,不动其它显式深链)。
function resolvePostAuthLanding(target, learnUrl) {
  var t = String(target || "");
  if (shouldLandOnDoubleWheel() && t.indexOf("/pages/chat/chat") >= 0) {
    return learnUrl;
  }
  return target;
}

module.exports = {
  getWorkspaceFlags: getWorkspaceFlags,
  isWorkspaceEnabled: isWorkspaceEnabled,
  isFeatureEnabled: isFeatureEnabled,
  shouldShowWorkspaceShell: shouldShowWorkspaceShell,
  shouldLandOnDoubleWheel: shouldLandOnDoubleWheel,
  resolveTeachingVideoLimit: resolveTeachingVideoLimit,
  resolvePostAuthLanding: resolvePostAuthLanding,
  getFeatureByRoute: getFeatureByRoute,
  isRouteEnabled: isRouteEnabled,
  resolveShellList: resolveShellList,
  ensureFeatureEnabled: ensureFeatureEnabled,
};
