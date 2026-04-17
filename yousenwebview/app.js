// app.js
const TOKEN_KEY = "auth_token";
const USER_ID_KEY = "auth_user_id";
const DEEPTUTOR_ENTRY_KEY = "deeptutor_entry_enabled";
const DEEPTUTOR_ENTRY_CONFIG_KEY = "deeptutor_entry_config";
const DEEPTUTOR_WORKSPACE_FLAGS_KEY = "deeptutor_workspace_flags";

const ENV_VERSION =
  (typeof __wxConfig !== "undefined" && __wxConfig.envVersion) || "release";
const IS_DEVELOP = ENV_VERSION === "develop";
const IS_TRIAL = ENV_VERSION === "trial";
const IS_DEVTOOLS =
  typeof __wxConfig !== "undefined" && __wxConfig.platform === "devtools";

const PROD_GATEWAY =
  (typeof __PROD_GATEWAY__ !== "undefined" && __PROD_GATEWAY__) ||
  "https://test2.yousenjiaoyu.com";
const PROD_API =
  (typeof __PROD_API__ !== "undefined" && __PROD_API__) ||
  "https://test2.yousenjiaoyu.com";
const NGROK_URL =
  (typeof __NGROK_URL__ !== "undefined" && __NGROK_URL__) ||
  "https://test2.yousenjiaoyu.com";
const LOCAL_BASE_URL =
  (typeof __LOCAL_BASE_URL__ !== "undefined" && __LOCAL_BASE_URL__) ||
  "http://127.0.0.1:8001";
const USE_LOCAL_DEVTOOLS =
  typeof __USE_LOCAL_DEVTOOLS__ !== "undefined"
    ? __USE_LOCAL_DEVTOOLS__
    : false;
const HOST_SYS_INFO_KEY = "yousen_host_sys_info";
const DEFAULT_HOST_SYS_INFO = {
  is_audit: 0,
};
const DEFAULT_HOST_LAYOUT = {
  navHeight: 44,
  titleHeight: 44,
  fontSizeSetting: "28rpx",
};
const { getrq } = require("./utils/request");

let hostSysInfoPromise = null;

function getStoredToken() {
  return wx.getStorageSync(TOKEN_KEY) || null;
}

function clearStoredToken() {
  wx.removeStorageSync(TOKEN_KEY);
  wx.removeStorageSync(USER_ID_KEY);
}

function normalizeBooleanFlag(value, defaultValue) {
  if (value === undefined || value === null || value === "") {
    return defaultValue;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["0", "false", "off", "no", "disabled"].includes(normalized)) {
      return false;
    }
    if (["1", "true", "on", "yes", "enabled"].includes(normalized)) {
      return true;
    }
  }
  return Boolean(value);
}

function resolveDeeptutorEntryEnabled() {
  return normalizeBooleanFlag(wx.getStorageSync(DEEPTUTOR_ENTRY_KEY), true);
}

function getDefaultDeeptutorEntryConfig() {
  return {
    title: "鲁班AI智考",
    subtitle: "智能答疑入口",
    tip: "点击进入",
    badge: "AI",
    variant: "blue",
  };
}

function normalizeDeeptutorEntryVariant(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (normalized === "default") return "blue";
  if (normalized === "promo") return "orange";
  if (normalized === "compact") return "dark";
  if (normalized === "smart") return "teal";
  if (["blue", "orange", "teal", "dark"].includes(normalized)) {
    return normalized;
  }
  return "blue";
}

function normalizeDeeptutorEntryConfig(config) {
  const defaults = getDefaultDeeptutorEntryConfig();
  const source = config && typeof config === "object" ? config : {};
  return {
    title: String(source.title || source.text || defaults.title).trim() || defaults.title,
    subtitle:
      String(source.subtitle || source.subtext || defaults.subtitle).trim() ||
      defaults.subtitle,
    tip: String(source.tip || source.cta || defaults.tip).trim() || defaults.tip,
    badge:
      String(source.badge || source.iconText || defaults.badge).trim() ||
      defaults.badge,
    variant: normalizeDeeptutorEntryVariant(source.variant || defaults.variant),
  };
}

function resolveDeeptutorEntryConfig() {
  return normalizeDeeptutorEntryConfig(wx.getStorageSync(DEEPTUTOR_ENTRY_CONFIG_KEY));
}

function getDefaultDeeptutorWorkspaceFlags() {
  return {
    workspaceEnabled: true,
    historyEnabled: true,
    reportEnabled: true,
    profileEnabled: true,
    assessmentEnabled: true,
  };
}

function normalizeDeeptutorWorkspaceFlags(flags) {
  const defaults = getDefaultDeeptutorWorkspaceFlags();
  const source = flags && typeof flags === "object" ? flags : {};
  return {
    workspaceEnabled: normalizeBooleanFlag(
      source.workspaceEnabled !== undefined
        ? source.workspaceEnabled
        : source.workspace_enabled,
      defaults.workspaceEnabled
    ),
    historyEnabled: normalizeBooleanFlag(
      source.historyEnabled !== undefined
        ? source.historyEnabled
        : source.history_enabled,
      defaults.historyEnabled
    ),
    reportEnabled: normalizeBooleanFlag(
      source.reportEnabled !== undefined
        ? source.reportEnabled
        : source.report_enabled,
      defaults.reportEnabled
    ),
    profileEnabled: normalizeBooleanFlag(
      source.profileEnabled !== undefined
        ? source.profileEnabled
        : source.profile_enabled,
      defaults.profileEnabled
    ),
    assessmentEnabled: normalizeBooleanFlag(
      source.assessmentEnabled !== undefined
        ? source.assessmentEnabled
        : source.assessment_enabled,
      defaults.assessmentEnabled
    ),
  };
}

function resolveDeeptutorWorkspaceFlags() {
  return normalizeDeeptutorWorkspaceFlags(
    wx.getStorageSync(DEEPTUTOR_WORKSPACE_FLAGS_KEY)
  );
}

function normalizeHostSysInfo(sysInfo) {
  const source = sysInfo && typeof sysInfo === "object" ? sysInfo : {};
  let isAudit = source.is_audit;
  if (isAudit === undefined || isAudit === null || isAudit === "") {
    isAudit = DEFAULT_HOST_SYS_INFO.is_audit;
  }
  if (typeof isAudit === "boolean") {
    isAudit = isAudit ? 1 : 0;
  } else if (typeof isAudit === "string") {
    const normalized = isAudit.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) {
      isAudit = 1;
    } else if (["0", "false", "no", "off"].includes(normalized)) {
      isAudit = 0;
    }
  }
  return {
    ...DEFAULT_HOST_SYS_INFO,
    ...source,
    is_audit: Number(isAudit) === 1 ? 1 : 0,
  };
}

function readStoredHostSysInfo() {
  return normalizeHostSysInfo(wx.getStorageSync(HOST_SYS_INFO_KEY));
}

function getHostWindowInfo() {
  if (wx.getWindowInfo) {
    try {
      return wx.getWindowInfo() || {};
    } catch (error) {}
  }
  try {
    return wx.getSystemInfoSync() || {};
  } catch (error) {
    return {};
  }
}

function resolveHostLayout() {
  try {
    const systemInfo = getHostWindowInfo();
    const statusBarHeight = Number(systemInfo.statusBarHeight) || 0;
    const navHeight = statusBarHeight > 0 ? statusBarHeight + 44 : 44;
    return {
      navHeight,
      titleHeight: navHeight,
      fontSizeSetting: DEFAULT_HOST_LAYOUT.fontSizeSetting,
    };
  } catch (error) {
    return { ...DEFAULT_HOST_LAYOUT };
  }
}

function extractDeeptutorEntryEnabled(payload) {
  var containers = [];
  var push = function (value) {
    if (value && typeof value === "object") {
      containers.push(value);
    }
  };
  push(payload);
  if (payload && typeof payload === "object") {
    push(payload.data);
    push(payload.config);
    push(payload.flags);
    push(payload.feature_flags);
    push(payload.settings);
  }

  for (var i = 0; i < containers.length; i++) {
    var item = containers[i];
    if (!item || typeof item !== "object") continue;
    if (item.deeptutorEntryEnabled !== undefined) {
      return normalizeBooleanFlag(item.deeptutorEntryEnabled, true);
    }
    if (item.deeptutor_entry_enabled !== undefined) {
      return normalizeBooleanFlag(item.deeptutor_entry_enabled, true);
    }
    if (item.aiEntryEnabled !== undefined) {
      return normalizeBooleanFlag(item.aiEntryEnabled, true);
    }
    if (item.ai_entry_enabled !== undefined) {
      return normalizeBooleanFlag(item.ai_entry_enabled, true);
    }
    if (item.lubanAiEntryEnabled !== undefined) {
      return normalizeBooleanFlag(item.lubanAiEntryEnabled, true);
    }
    if (item.luban_ai_entry_enabled !== undefined) {
      return normalizeBooleanFlag(item.luban_ai_entry_enabled, true);
    }
  }
  return null;
}

function extractDeeptutorEntryConfig(payload) {
  var containers = [];
  var push = function (value) {
    if (value && typeof value === "object") {
      containers.push(value);
    }
  };
  push(payload);
  if (payload && typeof payload === "object") {
    push(payload.data);
    push(payload.config);
    push(payload.flags);
    push(payload.feature_flags);
    push(payload.settings);
    push(payload.deeptutor_entry);
    push(payload.deeptutorEntry);
  }

  for (var i = 0; i < containers.length; i++) {
    var item = containers[i];
    if (!item || typeof item !== "object") continue;
    if (item.deeptutor_entry && typeof item.deeptutor_entry === "object") {
      return normalizeDeeptutorEntryConfig(item.deeptutor_entry);
    }
    if (item.deeptutorEntry && typeof item.deeptutorEntry === "object") {
      return normalizeDeeptutorEntryConfig(item.deeptutorEntry);
    }
    if (
      item.deeptutor_entry_text !== undefined ||
      item.deeptutor_entry_title !== undefined ||
      item.deeptutor_entry_subtitle !== undefined ||
      item.deeptutor_entry_tip !== undefined ||
      item.deeptutor_entry_badge !== undefined ||
      item.deeptutor_entry_variant !== undefined
    ) {
      return normalizeDeeptutorEntryConfig({
        title: item.deeptutor_entry_title || item.deeptutor_entry_text,
        subtitle: item.deeptutor_entry_subtitle,
        tip: item.deeptutor_entry_tip,
        badge: item.deeptutor_entry_badge,
        variant: item.deeptutor_entry_variant,
      });
    }
    if (
      item.deeptutorEntryTitle !== undefined ||
      item.deeptutorEntryText !== undefined ||
      item.deeptutorEntrySubtitle !== undefined ||
      item.deeptutorEntryTip !== undefined ||
      item.deeptutorEntryBadge !== undefined ||
      item.deeptutorEntryVariant !== undefined
    ) {
      return normalizeDeeptutorEntryConfig({
        title: item.deeptutorEntryTitle || item.deeptutorEntryText,
        subtitle: item.deeptutorEntrySubtitle,
        tip: item.deeptutorEntryTip,
        badge: item.deeptutorEntryBadge,
        variant: item.deeptutorEntryVariant,
      });
    }
  }
  return null;
}

function extractDeeptutorWorkspaceFlags(payload) {
  var containers = [];
  var push = function (value) {
    if (value && typeof value === "object") {
      containers.push(value);
    }
  };
  push(payload);
  if (payload && typeof payload === "object") {
    push(payload.data);
    push(payload.config);
    push(payload.flags);
    push(payload.feature_flags);
    push(payload.settings);
    push(payload.deeptutor_workspace);
    push(payload.deeptutorWorkspace);
  }

  for (var i = 0; i < containers.length; i++) {
    var item = containers[i];
    if (!item || typeof item !== "object") continue;
    if (item.deeptutor_workspace && typeof item.deeptutor_workspace === "object") {
      return normalizeDeeptutorWorkspaceFlags(item.deeptutor_workspace);
    }
    if (item.deeptutorWorkspace && typeof item.deeptutorWorkspace === "object") {
      return normalizeDeeptutorWorkspaceFlags(item.deeptutorWorkspace);
    }
    if (
      item.deeptutor_workspace_enabled !== undefined ||
      item.deeptutor_history_enabled !== undefined ||
      item.deeptutor_report_enabled !== undefined ||
      item.deeptutor_profile_enabled !== undefined ||
      item.deeptutor_assessment_enabled !== undefined
    ) {
      return normalizeDeeptutorWorkspaceFlags({
        workspaceEnabled: item.deeptutor_workspace_enabled,
        historyEnabled: item.deeptutor_history_enabled,
        reportEnabled: item.deeptutor_report_enabled,
        profileEnabled: item.deeptutor_profile_enabled,
        assessmentEnabled: item.deeptutor_assessment_enabled,
      });
    }
    if (
      item.deeptutorWorkspaceEnabled !== undefined ||
      item.deeptutorHistoryEnabled !== undefined ||
      item.deeptutorReportEnabled !== undefined ||
      item.deeptutorProfileEnabled !== undefined ||
      item.deeptutorAssessmentEnabled !== undefined
    ) {
      return normalizeDeeptutorWorkspaceFlags({
        workspaceEnabled: item.deeptutorWorkspaceEnabled,
        historyEnabled: item.deeptutorHistoryEnabled,
        reportEnabled: item.deeptutorReportEnabled,
        profileEnabled: item.deeptutorProfileEnabled,
        assessmentEnabled: item.deeptutorAssessmentEnabled,
      });
    }
  }

  return null;
}

function resolveBaseUrl() {
  if (
    IS_DEVELOP &&
    IS_DEVTOOLS &&
    normalizeBooleanFlag(USE_LOCAL_DEVTOOLS, false)
  ) {
    return LOCAL_BASE_URL;
  }
  if (IS_DEVELOP || IS_TRIAL) {
    return NGROK_URL;
  }
  return PROD_API;
}

App({
  onLaunch() {
    wx.login({
      success: () => {},
    });

    const token = getStoredToken();
    if (token) {
      this.globalData.token = token;
    }

    const hostLayout = resolveHostLayout();
    const storedHostSysInfo = readStoredHostSysInfo();
    const baseUrl = resolveBaseUrl();
    this.globalData.theme = wx.getStorageSync("theme") || "dark";
    this.globalData.apiUrl = baseUrl;
    this.globalData.gatewayUrl = baseUrl;
    this.globalData.apiCandidates = [baseUrl];
    this.globalData.gatewayCandidates = [baseUrl];
    this.globalData.navHeight = hostLayout.navHeight;
    this.globalData.titleHeight = hostLayout.titleHeight;
    this.globalData.fontSizeSetting = hostLayout.fontSizeSetting;
    this.globalData.sysInfo = storedHostSysInfo;
    this.globalData.sysInfoLoaded = !!wx.getStorageSync(HOST_SYS_INFO_KEY);
    this.globalData.deeptutorEntryEnabled = resolveDeeptutorEntryEnabled();
    this.globalData.deeptutorEntryConfig = resolveDeeptutorEntryConfig();
    this.globalData.deeptutorWorkspaceFlags = resolveDeeptutorWorkspaceFlags();

    wx.onNetworkStatusChange((res) => {
      this.globalData.networkAvailable = res.isConnected;
      if (!res.isConnected) {
        wx.showToast({ title: "网络已断开", icon: "none", duration: 2000 });
      }
    });

    wx.getNetworkType({
      success: (res) => {
        this.globalData.networkAvailable = res.networkType !== "none";
      },
    });
  },

  checkAuth(callback) {
    const token = getStoredToken();
    if (!token) {
      const pages = getCurrentPages();
      const currentRoute =
        pages && pages.length ? pages[pages.length - 1].route || "" : "";
      if (currentRoute === "packageDeeptutor/pages/login/login") {
        return;
      }
      if (this.globalData._authRedirecting) {
        return;
      }
      this.globalData._authRedirecting = true;
      wx.reLaunch({
        url: "/packageDeeptutor/pages/login/login",
        complete: () => {
          this.globalData._authRedirecting = false;
        },
      });
      return;
    }
    this.globalData.token = token;
    this.globalData.userId = wx.getStorageSync(USER_ID_KEY) || null;
    if (callback) callback(token);
  },

  getHostSysInfo(force = false) {
    if (!force && this.globalData.sysInfoLoaded) {
      return Promise.resolve(
        this.globalData.sysInfo || normalizeHostSysInfo()
      );
    }
    if (hostSysInfoPromise) {
      return hostSysInfoPromise;
    }
    hostSysInfoPromise = getrq("GetSysInfo")
      .then((res) => {
        const nextSysInfo =
          res && res.status == 1 && res.data && typeof res.data === "object"
            ? normalizeHostSysInfo(res.data)
            : this.globalData.sysInfo || normalizeHostSysInfo();
        this.globalData.sysInfo = nextSysInfo;
        this.globalData.sysInfoLoaded = true;
        wx.setStorageSync(HOST_SYS_INFO_KEY, nextSysInfo);
        return nextSysInfo;
      })
      .catch(() => {
        this.globalData.sysInfoLoaded = !!wx.getStorageSync(HOST_SYS_INFO_KEY);
        return this.globalData.sysInfo || normalizeHostSysInfo();
      })
      .finally(() => {
        hostSysInfoPromise = null;
      });
    return hostSysInfoPromise;
  },

  getDeeptutorEntryEnabled() {
    return normalizeBooleanFlag(
      this.globalData.deeptutorEntryEnabled,
      true
    );
  },

  getDeeptutorEntryConfig() {
    return normalizeDeeptutorEntryConfig(this.globalData.deeptutorEntryConfig);
  },

  setDeeptutorEntryEnabled(enabled) {
    const normalized = normalizeBooleanFlag(enabled, true);
    this.globalData.deeptutorEntryEnabled = normalized;
    wx.setStorageSync(DEEPTUTOR_ENTRY_KEY, normalized);
    return normalized;
  },

  setDeeptutorEntryConfig(config) {
    const normalized = normalizeDeeptutorEntryConfig(config);
    this.globalData.deeptutorEntryConfig = normalized;
    wx.setStorageSync(DEEPTUTOR_ENTRY_CONFIG_KEY, normalized);
    return normalized;
  },

  getDeeptutorWorkspaceFlags() {
    return normalizeDeeptutorWorkspaceFlags(this.globalData.deeptutorWorkspaceFlags);
  },

  setDeeptutorWorkspaceFlags(flags) {
    const normalized = normalizeDeeptutorWorkspaceFlags(flags);
    this.globalData.deeptutorWorkspaceFlags = normalized;
    wx.setStorageSync(DEEPTUTOR_WORKSPACE_FLAGS_KEY, normalized);
    return normalized;
  },

  syncDeeptutorEntryFlagFromPayload(payload) {
    const nextValue = extractDeeptutorEntryEnabled(payload);
    const nextConfig = extractDeeptutorEntryConfig(payload);
    const nextWorkspaceFlags = extractDeeptutorWorkspaceFlags(payload);
    if (nextConfig) {
      this.setDeeptutorEntryConfig(nextConfig);
    }
    if (nextWorkspaceFlags) {
      this.setDeeptutorWorkspaceFlags(nextWorkspaceFlags);
    }
    if (nextValue === null) {
      return this.getDeeptutorEntryEnabled();
    }
    return this.setDeeptutorEntryEnabled(nextValue);
  },

  logout() {
    clearStoredToken();
    this.globalData.token = null;
    this.globalData.userId = null;
    this.globalData.userInfo = null;
    if (this.globalData._authRedirecting) {
      return;
    }
    this.globalData._authRedirecting = true;
    wx.reLaunch({
      url: "/packageDeeptutor/pages/login/login",
      complete: () => {
        this.globalData._authRedirecting = false;
      },
    });
  },

  globalData: {
    userInfo: null,
    pathurl_route: null,
    token: null,
    userId: null,
    goHomeFlag: false,
    pendingChatQuery: "",
    pendingChatMode: "AUTO",
    pendingConversationId: null,
    gatewayUrl: "",
    apiUrl: "",
    gatewayCandidates: [],
    apiCandidates: [],
    navHeight: DEFAULT_HOST_LAYOUT.navHeight,
    titleHeight: DEFAULT_HOST_LAYOUT.titleHeight,
    fontSizeSetting: DEFAULT_HOST_LAYOUT.fontSizeSetting,
    sysInfo: { ...DEFAULT_HOST_SYS_INFO },
    sysInfoLoaded: false,
    chatEngine: "deeptutor",
    theme: "dark",
    networkAvailable: true,
    deeptutorEntryEnabled: true,
    deeptutorEntryConfig: getDefaultDeeptutorEntryConfig(),
    deeptutorWorkspaceFlags: getDefaultDeeptutorWorkspaceFlags(),
    _authRedirecting: false,
  },
});
