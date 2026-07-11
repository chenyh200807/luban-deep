// pages/chat/chat.js — 1:1 复刻 Web 手机端
var auth = require("../../utils/auth");
var api = require("../../utils/api");
var unwrap = api.unwrapResponse;
var aiMessageState = require("../../utils/ai-message-state");
var wsStream = require("../../utils/ws-stream");
var helpers = require("../../utils/helpers");
var log = require("../../utils/logger");
var workflowStatus = require("../../utils/workflow-status");
var citationFormat = require("../../utils/citation-format");
var chatTurnRecovery = require("../../utils/chat-turn-recovery");
var markdownFixtures = null;
var surfaceTelemetry = require("../../utils/surface-telemetry");
var runtime = require("../../utils/runtime");
var historyTombstone = require("../../utils/history-tombstone");
var route = require("../../utils/route");
var flags = require("../../utils/flags");
var analytics = require("../../utils/analytics");
var learningHomeViewModel = require("../../utils/learning-home-view-model");

function trackBehavior(eventName, payload) {
  if (surfaceTelemetry && typeof surfaceTelemetry.trackProductBehavior === "function") {
    surfaceTelemetry.trackProductBehavior(eventName, payload);
  }
}

// ── 常量（部分由性能分级动态覆盖）──────────────
var _animCfg = helpers.getAnimConfig();
var FLUSH_THROTTLE_MS = _animCfg.flushThrottleMs; // token 刷新节流
var MD_PARSE_INTERVAL = _animCfg.mdParseInterval; // 每 N 次 flush 解析一次 Markdown
var MAX_MESSAGES = 200; // 内存中最大消息数
var INPUT_DEBOUNCE_MS = 80; // 输入防抖
var HERO_MAX_DRAG_PX = 84; // Hero 拖拽最大位移
var HERO_DRAG_DAMPING = 0.32; // Hero 拖拽阻尼
var HERO_VIBRATE_THRESHOLD_PX = 40; // Hero 拖拽震动阈值
var SCROLL_TOGGLE_COOLDOWN_MS = 300; // 滚动切换 tab bar 冷却
var VIEWPORT_MARGIN_PX = 600; // IntersectionObserver 上下扩展边距
var CHAT_TOOL_PREFS_KEY = "chat_tool_prefs";
var DEFAULT_WEB_SEARCH_AVAILABLE = false;

function getMarkdownFixtures() {
  if (!markdownFixtures) {
    markdownFixtures = require("../../utils/devtools-markdown-fixtures");
  }
  return markdownFixtures;
}
var NAVBAR_INNER_HEIGHT_RPX = 128;
var _IS_DEVTOOLS =
  typeof __wxConfig !== "undefined" && __wxConfig.platform === "devtools";
var HISTORY_CACHE_KEY = "history_cache";
var HISTORY_CACHE_KEY_ARCHIVED = "history_cache_archived";
var CHAT_PENDING_TURN_KEY = "chat_pending_turn_v1";
var PENDING_TURN_MAX_AGE_MS = 30 * 60 * 1000;
var PENDING_TURN_POLL_MAX_ATTEMPTS = 1200;
var PENDING_TURN_POLL_DELAY_MS = 1500;
var PENDING_TURN_FOREGROUND_MAX_ATTEMPTS = 4;
var HYDRATED_HISTORY_EAGER_AI_MESSAGES = 8;
var HOME_DASHBOARD_CACHE_KEY = "deeptutor.chat.homeDashboard.v2";
var HOME_DASHBOARD_CACHE_MAX_AGE_MS = 10 * 60 * 1000;

function isLocalDraftSessionId(id) {
  return /^s_\d{10,}$/.test(String(id || "").trim());
}

function normalizePendingTurn(raw) {
  var source = raw && typeof raw === "object" ? raw : {};
  var conversationId = String(source.conversationId || "").trim();
  if (!conversationId) return null;
  if (isLocalDraftSessionId(conversationId)) return null;
  var createdAt = Number(source.createdAt) || Date.now();
  if (Date.now() - createdAt > PENDING_TURN_MAX_AGE_MS) return null;
  return {
    conversationId: conversationId,
    baselineCount: Math.max(0, Number(source.baselineCount) || 0),
    query: String(source.query || ""),
    clientTurnId: String(source.clientTurnId || ""),
    turnId: String(source.turnId || ""),
    createdAt: createdAt,
  };
}

/**
 * 10d 上下文带入条文案：只读既有载体（followupQuestionContext / promptIntent），
 * 不新增任何请求字段；派生不出对象名时返回空串（无上下文不渲染）。
 */
function buildContextBannerLabel(followupQuestionContext, promptIntent) {
  var ctx =
    followupQuestionContext && typeof followupQuestionContext === "object"
      ? followupQuestionContext
      : null;
  var intent = promptIntent && typeof promptIntent === "object" ? promptIntent : null;
  if (ctx) {
    if (Array.isArray(ctx.items) && ctx.items.length > 1) {
      return "已带入：本组 " + ctx.items.length + " 题作答";
    }
    var stem = String(ctx.question || "").replace(/\s+/g, " ").trim();
    if (stem) {
      return "已带入：" + (stem.length > 14 ? stem.slice(0, 14) + "…" : stem);
    }
    if (ctx.question_id) return "已带入：当前题目";
  }
  if (intent && String(intent.source || "") === "teach_card") {
    var label = String(
      intent.concept_label || intent.scene_title || intent.concept_id || "",
    ).trim();
    if (label) return "已带入：" + label + " · 讲懂卡";
  }
  return "";
}

function safeDecodeURIComponent(value) {
  var text = String(value || "");
  if (!text) return "";
  try {
    return decodeURIComponent(text);
  } catch (_) {
    return text;
  }
}

function getNavRightInset(info) {
  try {
    if (wx && typeof wx.getMenuButtonBoundingClientRect === "function") {
      var rect = wx.getMenuButtonBoundingClientRect();
      var width = info.windowWidth || info.screenWidth || 375;
      if (rect && rect.left && width > rect.left) {
        return Math.ceil(width - rect.left + 8);
      }
    }
  } catch (_) {}
  return 24;
}

function rememberDeletedConversationIds(ids) {
  historyTombstone.rememberDeletedConversationIds(ids);
}

function clearConversationHistoryCaches() {
  try {
    wx.removeStorageSync(HISTORY_CACHE_KEY);
    wx.removeStorageSync(HISTORY_CACHE_KEY_ARCHIVED);
  } catch (_) {}
}

function hasAssessmentSignal(raw) {
  var assessment = unwrap(raw) || raw || {};
  var diagnosticSources = assessment.diagnostic_sources;
  var firstRun =
    diagnosticSources && typeof diagnosticSources === "object"
      ? diagnosticSources.first_run
      : null;
  if (firstRun && firstRun.completed === true) return true;
  var level = String(assessment.level || "").trim();
  var chapterMastery = assessment.chapter_mastery;
  if (level) return true;
  if (!chapterMastery || typeof chapterMastery !== "object") return false;
  return Object.keys(chapterMastery).length > 0;
}

function resolveAssessmentTrainingCapability(promptIntent) {
  var intent = promptIntent && typeof promptIntent === "object" ? promptIntent : null;
  if (!intent) return "";
  var signal = String(intent.learning_signal_type || "").trim();
  if (signal !== "assessment_wrong_item_practice") return "";
  return "deep_question";
}

function isGenericFocusQuery(query) {
  var normalized = String(query || "").replace(/\s+/g, "");
  if (!normalized) return true;
  if (normalized.indexOf("学习计划") >= 0) return true;
  if (normalized.indexOf("下一步学习推进") >= 0) return true;
  if (normalized.indexOf("先判断我当前更适合") >= 0) return true;
  if (normalized.indexOf("继续巩固") === 0) return true;
  return ["继续我的计划", "继续计划", "继续学习", "按计划继续"].indexOf(normalized) >= 0;
}

function buildFocusDisplayTitle(focus, title) {
  var text = String(title || "")
    .replace(/^今日焦点[:：]\s*/, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return "";
  if (/第一份.*学习证据/.test(text) || /给系统.*学习证据/.test(text)) return "先做 1 题摸底";
  if (/^先做\s*1\s*题/.test(text)) return text;
  if (text && text !== "保持节奏，继续推进" && text !== "按当前状态推进建筑实务") return text;
  return "";
}

function buildFocusDisplayMeta(focus, meta) {
  var payload = focus && typeof focus === "object" ? focus : {};
  var text = String(meta || payload.meta || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  if (text === "starter") return "生成学情基线";
  if (/learner_state\.home_personalization/.test(text)) return "来自学情更新";
  return text.length > 8 ? "" : text;
}

function readCachedHomeDashboard() {
  try {
    if (typeof wx === "undefined" || typeof wx.getStorageSync !== "function") return null;
    var cached = wx.getStorageSync(HOME_DASHBOARD_CACHE_KEY);
    if (!cached || typeof cached !== "object") return null;
    if (Date.now() - (Number(cached.cachedAt) || 0) > HOME_DASHBOARD_CACHE_MAX_AGE_MS) return null;
    var dashboard =
      cached.dashboard && typeof cached.dashboard === "object" ? cached.dashboard : null;
    if (
      dashboard &&
      typeof learningHomeViewModel.isTrustedHomeDashboardPayload === "function" &&
      !learningHomeViewModel.isTrustedHomeDashboardPayload(dashboard)
    )
      return null;
    return dashboard;
  } catch (_) {
    return null;
  }
}

function writeCachedHomeDashboard(dashboard) {
  try {
    if (typeof wx === "undefined" || typeof wx.setStorageSync !== "function") return;
    if (!dashboard || typeof dashboard !== "object") return;
    if (
      typeof learningHomeViewModel.isTrustedHomeDashboardPayload === "function" &&
      !learningHomeViewModel.isTrustedHomeDashboardPayload(dashboard)
    )
      return;
    wx.setStorageSync(HOME_DASHBOARD_CACHE_KEY, {
      cachedAt: Date.now(),
      dashboard: dashboard,
    });
  } catch (_) {}
}

function buildHomeDashboardUpdate(dashboard) {
  var d = dashboard && typeof dashboard === "object" ? dashboard : {};
  var today = d.today || {};
  var homeModel = learningHomeViewModel.buildLearningHomeViewModel(d);
  var focus = d.today_focus || today.focus || {};

  var update = {};
  update.reviewCount = homeModel.reviewCount;

  update.focusLabel = homeModel.focusLabel;
  update.focusTone = homeModel.focusTone;
  update.focusTitle = buildFocusDisplayTitle(focus, homeModel.focusTitle);
  update.focusMeta = buildFocusDisplayMeta(focus, homeModel.focusMeta);
  update.focusText = update.focusTitle;
  update.focusQuery = homeModel.focusQuery;
  update.focusActionType = homeModel.focusActionType;
  update.focusPromptIntent = homeModel.focusPromptIntent;
  update.recommendedPrompts = homeModel.recommendedPrompts;
  update.showStaticExamples = !homeModel.recommendedPrompts.length;
  return update;
}

function normalizeAnswerMode(value) {
  var key = String(value || "").trim().toLowerCase();
  if (key === "deep" || key === "detailed" || key === "深度" || key === "精讲") return "DEEP";
  if (key === "fast" || key === "quick" || key === "快速" || key === "快答") return "FAST";
  if (key === "auto" || key === "smart" || key === "智能") return "AUTO";
  return "";
}

function resolveConversationAnswerMode(meta) {
  var payload = meta && typeof meta === "object" && !Array.isArray(meta) ? meta : {};
  var preferences =
    payload.preferences && typeof payload.preferences === "object" ? payload.preferences : {};
  var hints =
    preferences.interaction_hints && typeof preferences.interaction_hints === "object"
      ? preferences.interaction_hints
      : {};
  var candidates = [
    payload.effective_response_mode,
    payload.selected_mode,
    hints.effective_response_mode,
    hints.selected_mode,
    payload.requested_response_mode,
    payload.answer_mode,
    payload.mode,
    payload.response_mode,
    payload.teaching_mode,
    preferences.chat_mode,
    hints.requested_response_mode,
    hints.teaching_mode,
  ];
  for (var i = 0; i < candidates.length; i++) {
    var mode = normalizeAnswerMode(candidates[i]);
    if (mode) return mode;
  }
  return "";
}

function isDeletedConversationId(id) {
  var key = String(id || "").trim();
  if (!key) return false;
  if (!historyTombstone || typeof historyTombstone.readDeletedConversationIds !== "function") return false;
  var tombstones = historyTombstone.readDeletedConversationIds();
  return !!(tombstones && tombstones[key]);
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    navRightInset: 24,
    safeBottom: 0,
    viewportWidth: 375,
    viewportHeight: 0,
    contentHeight: 0,
    workspaceShellHeight: 0,
    workspaceShellHidden: false,
    keyboardHeight: 0,
    inputCursorSpacing: 24,
    heroBottomSpacer: 64,
    chatBottomSpacer: 220,
    bottomBarCompact: false,
    bottomBarStyle: "",
    hasMessages: false,
    messages: [],
    inputText: "",
    isStreaming: false,
    canStopStream: false,
    chatScrollTop: 0,
    scrollToId: "",
    chatScrollWithAnimation: false,
    answerMode: "AUTO",
    enableReason: false,
    enableWebSearch: false,
    webSearchAvailable: DEFAULT_WEB_SEARCH_AVAILABLE,
    feedbackMsgId: "",
    feedbackTags: [],
    feedbackComment: "",
    feedbackSubmitting: false,
    isDark: true,
    showInternalStatus: true,
    // 性能分级：控制 WXML 中动效开关
    enableOrbs: _animCfg.enableBreathingOrbs,
    enableMarquee: _animCfg.enableMarquee,
    enableMsgAnim: _animCfg.enableMsgAnimation,
    enableFocusPulse: _animCfg.enableFocusPulse,

    // Hero
    userName: "用户",
    timeGreeting: helpers.getTimeGreeting(),
    avatarChar: "U",
    reviewCount: 0,
    focusLabel: "今日焦点",
    focusTitle: "",
    focusMeta: "",
    focusTone: "plan",
    focusText: "",
    focusQuery: "",
    focusActionType: "",
    focusPromptIntent: null,
    recommendedPrompts: [],
    showStaticExamples: true,
    entrySource: "",
    // 10d 重铺：上下文带入条（数据源=既有 followupContext/promptIntent 载体，可见化而已）
    contextBanner: "",
    // 教学卡「问追AI」入口可预置占位文案；默认与原 placeholder 一致
    inputPlaceholder: "直接问建筑实务：考点、真题、规范、错题",
    workspaceBackVisible: false,
    workspaceBackLabel: "返回",
    profileEnabled: true,
    isGuestPreview: false,
    paywallVisible: false,
    paywallTitle: "",
    paywallText: "",

    // Hero 弹性拖拽
    _heroDragY: 0,
    _heroDragTransition: "none",

    examples: [
      {
        icon: "○",
        title: "概念入门",
        desc: "建筑构造基础",
        bgDark: "rgba(59,130,246,0.16)",
        fgDark: "#93c5fd",
        bgLight: "#e9f1ff",
        fgLight: "#4c72d4",
        query: "建筑构造是什么？",
      },
      {
        icon: "▧",
        title: "知识地图",
        desc: "建筑实务考点梳理",
        bgDark: "rgba(245,158,11,0.16)",
        fgDark: "#fbbf24",
        bgLight: "#fff4e0",
        fgLight: "#c88a2b",
        query: "帮我梳理一建建筑实务的核心考点",
      },
      {
        icon: "△",
        title: "对比分析",
        desc: "易混淆概念",
        bgDark: "rgba(96,165,250,0.12)",
        fgDark: "#7dd3fc",
        bgLight: "#edf4ff",
        fgLight: "#3b82f6",
        query: "防水等级和设防层数有什么区别？",
      },
      {
        icon: "☆",
        title: "真题解析",
        desc: "历年真题",
        bgDark: "rgba(59,130,246,0.16)",
        fgDark: "#93c5fd",
        bgLight: "#e9f1ff",
        fgLight: "#2f6bff",
        query: "分析一道钢筋保护层的真题",
      },
    ],
  },

  _sid: "",
  _counter: 0,
  _streamId: null,
  _buf: "",
  _timer: null,
  _abort: null,
  _inputTimer: null,
  _inputText: "",
  _flushCount: 0,
  _convId: null,
  _pendingTurn: null,
  _recoveringTurn: false,
  _pendingRecoveryActive: false,
  _sessionPersistTimer: null,
  _historyCacheTimer: null,
  _pendingHistoryTitle: "",
  _surfaceTurnId: "",
  _firstVisibleAckSent: false,
  _doneRenderedAckSent: false,
  _observer: null, // IntersectionObserver 用于懒解析 Markdown
  _visibleSet: {}, // 当前可见消息 id 集合
  _autoScrollEnabled: true,
  _chatReadyPromise: null,
  _heroDragFramePending: false,
  _heroDragNextY: 0,

  // ── 生命周期 ──────────────────────────────────

  onLoad: function (options) {
    trackBehavior("module_viewed", { module: "chat", action: "view" });
    var info = helpers.getWindowInfo();
    var savedToolPrefs = wx.getStorageSync(CHAT_TOOL_PREFS_KEY) || {};
    var pendingInitialConversationId =
      typeof runtime.peekPendingConversationId === "function"
        ? runtime.peekPendingConversationId()
        : "";
    var entrySource =
      (options && (options.entrySource || options.entry_source || options.source)) ||
      "";
    // 教学卡「问追AI」深链承接：归并到既有 entrySource 体系，不建第二套参数。
    // 上下文并入既有 promptIntent 载体（concept_id/concept_label 与学习证据字段对齐），
    // 随首问一次性发出后即清，不新建通道。
    var teachPackId = safeDecodeURIComponent(
      options && (options.pack_id || options.packId),
    ).trim();
    var teachSceneTitle = safeDecodeURIComponent(
      options && (options.scene_title || options.sceneTitle),
    ).trim();
    var isTeachCardEntry =
      String(entrySource || "").trim() === "teach_card" && !!(teachPackId || teachSceneTitle);
    this._teachEntryIntent = isTeachCardEntry
      ? {
          source: "teach_card",
          concept_id: teachPackId,
          concept_label: teachSceneTitle || teachPackId,
          scene_title: teachSceneTitle,
        }
      : null;
    var statusBarHeight = info.statusBarHeight || 44;
    var viewportWidth = info.windowWidth || info.screenWidth || 375;
    var navRightInset = getNavRightInset(info);
    var navInnerHeight = Math.round(
      (NAVBAR_INNER_HEIGHT_RPX * viewportWidth) / 750,
    );
    var navHeight = statusBarHeight + navInnerHeight;
    var viewportHeight = info.windowHeight || info.screenHeight || 812;
    var safeBottom = info.safeArea
      ? info.screenHeight - info.safeArea.bottom
      : 0;
    var contentHeight = Math.max(viewportHeight - navHeight, 320);
    var workspaceShellHeight =
      Math.round((viewportWidth * 140) / 750) + safeBottom;

    this._messageIndexMap = Object.create(null);

    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: navHeight,
      navRightInset: navRightInset,
      safeBottom: safeBottom,
      viewportWidth: viewportWidth,
      viewportHeight: viewportHeight,
      contentHeight: contentHeight,
      workspaceShellHeight: workspaceShellHeight,
      hasMessages: !!pendingInitialConversationId,
      isDark: helpers.isDark(),
      enableReason: false,
      webSearchAvailable: DEFAULT_WEB_SEARCH_AVAILABLE,
      enableWebSearch: DEFAULT_WEB_SEARCH_AVAILABLE && !!savedToolPrefs.enableWebSearch,
      entrySource: String(entrySource || "").trim(),
      contextBanner: this._teachEntryIntent
        ? buildContextBannerLabel(null, this._teachEntryIntent)
        : "",
      inputPlaceholder: isTeachCardEntry
        ? "针对这一站提问…"
        : "直接问建筑实务：考点、真题、规范、错题",
    });
    if (isTeachCardEntry && teachPackId) {
      this._resolveTeachEntryTitle(teachPackId);
    }
    if (savedToolPrefs.enableReason) {
      this._saveToolPrefs(false, DEFAULT_WEB_SEARCH_AVAILABLE && !!savedToolPrefs.enableWebSearch);
    }
    this._loadToolRuntimeCapabilities(savedToolPrefs);
    var debugMarkdownSample =
      _IS_DEVTOOLS && options && options.debugMarkdownSample
        ? String(options.debugMarkdownSample)
        : "";
    this._debugMarkdownSampleActive = !!debugMarkdownSample;
    if (debugMarkdownSample) {
      this.debugLoadMarkdownRegressionSample(debugMarkdownSample);
      return;
    }

    // [FIX-SESSION-1] 仅在 5 分钟内恢复 session（处理页面刷新），
    // 超时则开启新对话，防止所有问题堆积在同一个历史记录中
    var savedSessionId = wx.getStorageSync("current_session_id");
    var savedTs = wx.getStorageSync("current_session_ts") || 0;
    var SESSION_MAX_AGE_MS = 5 * 60 * 1000; // 5 分钟过期

    if (
      savedSessionId &&
      !isLocalDraftSessionId(savedSessionId) &&
      Date.now() - savedTs < SESSION_MAX_AGE_MS
    ) {
      this._sid = savedSessionId;
      this._convId = savedSessionId;
    } else {
      this._sid = "s_" + Date.now();
      this._convId = null;
      wx.removeStorageSync("current_session_id");
      wx.removeStorageSync("current_session_ts");
    }
    var pendingTurn = this._loadPendingTurn();
    if (pendingTurn) {
      this._sid = pendingTurn.conversationId;
      this._convId = pendingTurn.conversationId;
      this._scheduleSessionPersist(true);
      this.setData({
        hasMessages: true,
        isStreaming: false,
        canStopStream: false,
      });
    }

    runtime.initNetworkMonitor();
    this._syncWorkspaceChrome({
      hidden: !flags.shouldShowWorkspaceShell(),
      hasMessages: !!pendingInitialConversationId,
    });
  },

  onShow: function () {
    var self = this;
    var dark = helpers.isDark();
    var pendingConversationId =
      typeof runtime.peekPendingConversationId === "function"
        ? runtime.peekPendingConversationId()
        : "";
    if (pendingConversationId && !this.data.hasMessages) {
      this.setData({
        hasMessages: true,
        isStreaming: false,
        chatScrollWithAnimation: false,
      });
      this._syncWorkspaceChrome({ hasMessages: true });
    }
    this.setData({ isDark: dark });
    this._syncWorkspaceBack();
    this.setData({
      profileEnabled: flags.isFeatureEnabled("profile"),
    });
    this._setWorkspaceShellHidden(!this._shouldShowWorkspaceShell());
    if (this._debugMarkdownSampleActive) {
      if (this.data.hasMessages) {
        this._setupObserver();
      }
      return;
    }
    // 从其他页面点 logo 回来，清消息回到 Hero 主页
    if (runtime.consumeGoHomeFlag()) {
      this.clearMessages();
    }
    if (isDeletedConversationId(this._convId || this._sid || wx.getStorageSync("current_session_id"))) {
      this.clearMessages();
    }
    self.setData({ timeGreeting: helpers.getTimeGreeting() });
    var pendingConvId = runtime.consumePendingConversationId();
    var restoringConversation = false;
    if (pendingConvId) {
      restoringConversation = true;
      self._restoreConversation(pendingConvId);
    } else if (!this.data.hasMessages && this._convId && this._sid) {
      restoringConversation = true;
      self._restoreConversation(this._convId);
    }
    if (this._loadPendingTurn() && !this._pendingRecoveryActive) {
      this._startPendingTurnBackgroundRecovery();
    }
    var hasUsableAuth =
      typeof auth.isLoggedIn === "function" ? auth.isLoggedIn() : !!auth.getToken();
    if (hasUsableAuth) {
      self.setData({ isGuestPreview: false });
      self._ensureChatReady().catch(function (e) {
        log.warn("Chat", "chat profile bootstrap degraded: " + ((e && e.message) || e));
      });
      if (restoringConversation) {
        runtime.consumePendingChatIntent();
      } else {
        var pendingIntent = runtime.consumePendingChatIntent();
        if (pendingIntent.query && !self.data.isStreaming) {
          self.setData({ answerMode: pendingIntent.mode || "AUTO" });
          if (pendingIntent.promptIntent) {
            self._activeAssessmentTrainingIntent = pendingIntent.promptIntent;
          }
          self._send(pendingIntent.query, {
            promptIntent: pendingIntent.promptIntent || null,
            followupQuestionContext: pendingIntent.followupQuestionContext || null,
          });
        } else if (!self.data.hasMessages) {
          Promise.resolve(self._loadDashboard()).then(
            function () {
              if (!self.data.hasMessages) self._checkDiagnostic();
            },
            function () {
              if (!self.data.hasMessages) self._checkDiagnostic();
            },
          );
        }
      }
    } else {
      var guestPendingIntent = runtime.consumePendingChatIntent();
      if (guestPendingIntent.query && !self.data.hasMessages) {
        self._inputText = guestPendingIntent.query;
      }
      self.setData({
        isGuestPreview: true,
        userName: "同学",
        avatarChar: "L",
        focusTone: "plan",
        focusTitle: "",
        focusMeta: "",
        focusText: "",
        focusQuery: "",
        focusActionType: "",
        focusPromptIntent: null,
        recommendedPrompts: [],
        showStaticExamples: true,
        inputText: guestPendingIntent.query || self.data.inputText || "",
      });
    }
    // [FIX] 从后台切回时重建 observer（onHide 中已 teardown）
    if (this.data.hasMessages) {
      this._setupObserver();
    }
  },

  onHide: function () {
    // [FIX] 切后台时不中断流式会话，只暂停 observer 降低内存开销。
    // 切回 onShow 时流式输出继续，避免用户切 app 后内容断掉。
    // 只有 onUnload（页面销毁）才调 _stop() 中断连接。
    this._flushDeferredWrites();
    this._teardownObserver();
  },
  onUnload: function () {
    this._flushDeferredWrites();
    this._stop();
    this._teardownObserver();
  },

  _applyAuthProfile: function (raw) {
    var info = api.unwrapResponse(raw);
    var name = info.username || info.display_name || "用户";
    var nextState = {
      userName: name,
      avatarChar: name.charAt(0).toUpperCase(),
    };
    this.setData(nextState);
    return info;
  },

  _ensureChatReady: function () {
    var self = this;
    if (self._chatReadyPromise) {
      return self._chatReadyPromise;
    }
    var hasUsableAuth =
      typeof auth.isLoggedIn === "function" ? auth.isLoggedIn() : !!auth.getToken();
    if (!hasUsableAuth) {
      runtime.checkAuth(function () {});
      return Promise.reject(new Error("AUTH_EXPIRED"));
    }
    self._chatReadyPromise = api
      .getUserInfo()
      .then(function (raw) {
        var info = self._applyAuthProfile(raw);
        var phone = ((info && info.phone) || "").trim().replace(/\D/g, "");
        if (!phone || phone.length < 8) {
          self.setData({ isGuestPreview: true });
          runtime.redirectToLogin(route.chat({ preview: "1" }));
          throw new Error("PHONE_BIND_REQUIRED");
        }
      })
      .then(
        function (result) {
          self._chatReadyPromise = null;
          return result;
        },
        function (err) {
          self._chatReadyPromise = null;
          throw err;
        },
      );
    return self._chatReadyPromise;
  },

  // ── 虚拟滚动：IntersectionObserver 懒解析 ─────

  _setupObserver: function () {
    if (this._observer) return;
    // Guard: 老版本基础库不支持 createIntersectionObserver
    if (typeof this.createIntersectionObserver !== "function") {
      // 降级：立即解析所有未解析的 AI 消息
      var msgs = this.data.messages;
      var update = {};
      for (var i = 0; i < msgs.length; i++) {
        if (
          msgs[i].role === "ai" &&
          msgs[i].content &&
          !msgs[i].hasStructuredContent &&
          (!msgs[i].blocks || !msgs[i].blocks.length)
        ) {
          var normalized = this._buildAiMessageUpdates(i, { parseBlocks: true });
          if (normalized) Object.assign(update, normalized.updates);
        }
      }
      if (Object.keys(update).length > 0) this.setData(update);
      return;
    }
    var self = this;
    this._observer = this.createIntersectionObserver({
      observeAll: true,
    });
    // 视口上下各扩展 VIEWPORT_MARGIN_PX，提前解析缓冲区消息
    this._observer
      .relativeTo(".content", {
        top: VIEWPORT_MARGIN_PX,
        bottom: VIEWPORT_MARGIN_PX,
      })
      .observe(".msg.ai", function (res) {
        if (!res || !res.id) return;
        // res.id = "msg-a5" → msgId = "a5"
        var msgId = res.id.replace("msg-", "");
        if (res.intersectionRatio > 0) {
          // 进入视口 → 解析 Markdown
          self._visibleSet[msgId] = true;
          self._lazyParseBlocks(msgId);
        } else {
          // 离开视口后保留已解析内容，避免消息高度突变导致阅读位置跳动
          delete self._visibleSet[msgId];
        }
      });
  },

  _teardownObserver: function () {
    if (this._observer) {
      this._observer.disconnect();
      this._observer = null;
    }
    this._visibleSet = {};
  },

  _loadPendingTurn: function () {
    var pending = null;
    try {
      pending = normalizePendingTurn(wx.getStorageSync(CHAT_PENDING_TURN_KEY));
    } catch (_) {
      pending = null;
    }
    if (!pending) {
      try {
        wx.removeStorageSync(CHAT_PENDING_TURN_KEY);
      } catch (_) {}
      return null;
    }
    this._pendingTurn = pending;
    return pending;
  },

  _persistPendingTurn: function (pending) {
    var normalized = normalizePendingTurn(pending);
    if (!normalized) return null;
    this._pendingTurn = normalized;
    try {
      wx.setStorageSync(CHAT_PENDING_TURN_KEY, normalized);
    } catch (_) {}
    return normalized;
  },

  _updatePendingTurn: function (patch) {
    var current = this._pendingTurn || this._loadPendingTurn();
    if (!current) return null;
    return this._persistPendingTurn(Object.assign({}, current, patch || {}));
  },

  _clearPendingTurn: function () {
    this._pendingTurn = null;
    this._pendingRecoveryActive = false;
    try {
      wx.removeStorageSync(CHAT_PENDING_TURN_KEY);
    } catch (_) {}
  },

  _isPendingTurnCurrent: function (pending) {
    var current = this._pendingTurn;
    if (!current || !pending) return false;
    return (
      current.conversationId === pending.conversationId &&
      current.clientTurnId === pending.clientTurnId &&
      Number(current.createdAt || 0) === Number(pending.createdAt || 0)
    );
  },

  _releaseStalePendingRecoveryForManualSend: function () {
    if (!this.data.isStreaming || !this._pendingRecoveryActive || this._abort) {
      return false;
    }
    this._recoveringTurn = false;
    this._clearPendingTurn();
    var hasMessages = !!(this.data.messages && this.data.messages.length);
    this.setData({
      hasMessages: hasMessages,
      isStreaming: false,
      chatScrollWithAnimation: false,
    });
    this._syncWorkspaceChrome({ hasMessages: hasMessages });
    return true;
  },

  _startPendingTurnBackgroundRecovery: function () {
    var self = this;
    if (!this._loadPendingTurn() || this._pendingRecoveryActive) return;
    this._pendingRecoveryActive = true;
    this._recoveringTurn = true;
    this.setData({
      hasMessages: true,
      isStreaming: false,
      canStopStream: false,
    });
    this._syncWorkspaceChrome({ hasMessages: true });
    this._recoverTurnFromHistory({
      maxAttempts: PENDING_TURN_FOREGROUND_MAX_ATTEMPTS,
      unlockOnExhausted: true,
      keepPendingOnExhausted: true,
      hydrateOnExhausted: false,
    }).then(function (recovered) {
      self._pendingRecoveryActive = false;
      if (!recovered) {
        self._recoveringTurn = false;
        self._continuePendingTurnRecoveryInBackground();
      }
    }, function () {
      self._pendingRecoveryActive = false;
      self._recoveringTurn = false;
      self._continuePendingTurnRecoveryInBackground();
    });
  },

  _continuePendingTurnRecoveryInBackground: function () {
    var self = this;
    if (!this._isPendingTurnCurrent(this._pendingTurn || this._loadPendingTurn()) || this._pendingRecoveryActive) return;
    this._pendingRecoveryActive = true;
    this._recoverTurnFromHistory({
      longPoll: true,
      unlockOnExhausted: true,
      keepPendingOnExhausted: true,
      hydrateOnExhausted: false,
    }).then(function (recovered) {
      self._pendingRecoveryActive = false;
      if (!recovered) {
        self._recoveringTurn = false;
      }
    }, function () {
      self._pendingRecoveryActive = false;
      self._recoveringTurn = false;
    });
  },

  _hydrateConversationMessages: function (rawMsgs) {
    var counter = 0;
    var sourceMsgs = rawMsgs || [];
    if (sourceMsgs.length > MAX_MESSAGES) {
      sourceMsgs = sourceMsgs.slice(sourceMsgs.length - MAX_MESSAGES);
    }
    var eagerAiRemaining = HYDRATED_HISTORY_EAGER_AI_MESSAGES;
    var eagerByIndex = {};
    for (var sourceIndex = sourceMsgs.length - 1; sourceIndex >= 0; sourceIndex--) {
      var sourceMsg = sourceMsgs[sourceIndex] || {};
      var sourceRole = sourceMsg.role === "assistant" ? "ai" : sourceMsg.role;
      if (sourceRole !== "ai") continue;
      var sourceAssistantText =
        typeof chatTurnRecovery.getAssistantDisplayText === "function"
          ? chatTurnRecovery.getAssistantDisplayText(sourceMsg)
          : "";
      if (
        !sourceMsg.content &&
        !sourceMsg.presentation &&
        !sourceAssistantText
      ) continue;
      if (eagerAiRemaining <= 0) break;
      eagerByIndex[sourceIndex] = true;
      eagerAiRemaining--;
    }
    var msgs = sourceMsgs.map(function (m, sourceIndex) {
      var role = m.role === "assistant" ? "ai" : m.role;
      var sourceContent =
        role === "ai" && typeof chatTurnRecovery.getAssistantDisplayText === "function"
          ? chatTurnRecovery.getAssistantDisplayText(m)
          : m.content || "";
      var visibleContent = aiMessageState.coerceUserVisibleContent(sourceContent || "");
      var visiblePresentation = aiMessageState.sanitizePresentationForState
        ? aiMessageState.sanitizePresentationForState(m.presentation)
        : m.presentation && typeof m.presentation === "object"
          ? m.presentation
          : null;
      var msg = {
        id: role.charAt(0) + counter++,
        role: role,
        content: visibleContent,
        renderableContent: "",
        streaming: false,
        blocks: [],
        hasStructuredContent: false,
        presentation: visiblePresentation,
        mcqCards: null,
        mcqHint: "",
        mcqReceipt: "",
        mcqInteractiveReady: false,
        mcqReviewMode: false,
        originalContent: "",
        originalExpanded: false,
        thinkingStatus: "",
        thinkingBadge: "",
        thinkingSub: "",
        thinkingTone: "",
        workflowEntries: [],
        workflowExpanded: false,
        workflowBadge: "",
        workflowTitle: "",
        workflowSub: "",
        workflowMeta: "",
        workflowCountText: "",
        workflowToggleText: "查看处理摘要",
        workflowTone: "compose",
        workflowActive: false,
        citations: null,
        engine: "",
        engineSessionId: "",
        engineTurnId: String(m.engine_turn_id || m.turn_id || ""),
        runtimeMeta: null,
        runtimeMetaText: "",
        billing: null,
        feedback: "",
      };
      if (role === "ai" && (visibleContent || msg.presentation)) {
        var shouldParseHistoryBlocks = !!eagerByIndex[sourceIndex];
        var derived = aiMessageState.deriveAiMessageRenderState({
          content: visibleContent,
          presentation: msg.presentation,
          parseBlocks: shouldParseHistoryBlocks,
        });
        msg.renderableContent = derived.renderableContent;
        msg.blocks = derived.blocks || [];
        msg.hasStructuredContent = !!derived.hasStructuredContent;
        msg.mcqCards = derived.mcqCards;
        msg.mcqHint = derived.mcqHint;
        msg.mcqReceipt = derived.mcqReceipt;
        msg.mcqInteractiveReady = derived.mcqInteractiveReady;
        msg.mcqReviewMode = derived.mcqReviewMode;
        msg.originalContent = derived.originalContent || "";
        msg.originalExpanded = derived.originalCollapsed === false;
      }
      return msg;
    });
    return {
      messages: msgs,
      counter: counter,
    };
  },

  _applyHydratedConversationMessages: function (rawMsgs, conversationMeta) {
    var self = this;
    var hydrated = this._hydrateConversationMessages(rawMsgs || []);
    var restoredMode = resolveConversationAnswerMode(conversationMeta);
    var update = {
      messages: hydrated.messages,
      hasMessages: hydrated.messages.length > 0,
      isStreaming: false,
      scrollToId: "msg-bottom",
      chatScrollWithAnimation: false,
    };
    if (restoredMode) {
      update.answerMode = restoredMode;
      if (restoredMode !== "DEEP") update.enableReason = false;
    }
    this._teardownObserver();
    this._counter = hydrated.counter;
    this._syncMessageIndexMap(hydrated.messages);
    this.setData(update);
    this._syncWorkspaceChrome({ hasMessages: hydrated.messages.length > 0 });
    setTimeout(function () {
      self._releaseBottomAnchor();
    }, 80);
    setTimeout(function () {
      self._setupObserver();
    }, 50);
  },

  _finishPendingTurnRecovery: function (serverMessages, options) {
    var hasServerMessages = Array.isArray(serverMessages);
    var keepPending = !!(options && options.keepPending);
    var shouldHydrate = !(options && options.hydrate === false);
    this._recoveringTurn = false;
    if (keepPending) {
      this._pendingRecoveryActive = false;
    } else {
      this._clearPendingTurn();
    }
    if (hasServerMessages && shouldHydrate) {
      this._applyHydratedConversationMessages(serverMessages);
      return;
    }
    var hasMessages = !!(this.data.messages && this.data.messages.length);
    this.setData({
      hasMessages: hasMessages,
      isStreaming: false,
      canStopStream: false,
      chatScrollWithAnimation: false,
    });
    this._syncWorkspaceChrome({ hasMessages: hasMessages });
  },

  debugReplaceMessagesWithStructuredSample: function (sample) {
    if (!_IS_DEVTOOLS) {
      log.warn("Chat", "debugReplaceMessagesWithStructuredSample is devtools-only");
      return false;
    }
    var payload = sample && typeof sample === "object" ? sample : {};
    var aiMsg = {
      id: "a" + this._counter++,
      role: "ai",
      content: String(payload.content || ""),
      renderableContent: "",
      streaming: false,
      blocks: [],
      hasStructuredContent: false,
      presentation: payload.presentation && typeof payload.presentation === "object" ? payload.presentation : null,
      mcqCards: null,
      mcqHint: "",
      mcqReceipt: "",
      mcqInteractiveReady: false,
      mcqReviewMode: false,
      originalContent: "",
      originalExpanded: false,
      thinkingStatus: "",
      thinkingBadge: "",
      thinkingSub: "",
      thinkingTone: "",
      workflowEntries: [],
      workflowExpanded: false,
      workflowBadge: "",
      workflowTitle: "",
      workflowSub: "",
      workflowMeta: "",
      workflowCountText: "",
      workflowToggleText: "查看处理摘要",
      workflowTone: "compose",
      workflowActive: false,
      citations: null,
      engine: "fixture",
      engineSessionId: "",
      engineTurnId: "",
      runtimeMeta: null,
      runtimeMetaText: "",
      billing: null,
      feedback: "",
    };
    this._teardownObserver();
    this.setData({
      messages: [aiMsg],
      hasMessages: true,
      isStreaming: false,
      scrollToId: "msg-bottom",
      chatScrollWithAnimation: false,
    });
    var normalized = this._buildAiMessageUpdates(0, {
      content: aiMsg.content,
      presentation: aiMsg.presentation,
      parseBlocks: true,
    });
    if (normalized) {
      this.setData(normalized.updates);
    }
    var self = this;
    setTimeout(function () {
      self._releaseBottomAnchor();
    }, 80);
    setTimeout(function () {
      self._setupObserver();
    }, 50);
    return true;
  },

  debugListMarkdownRegressionSamples: function () {
    if (!_IS_DEVTOOLS) {
      log.warn("Chat", "debugListMarkdownRegressionSamples is devtools-only");
      return [];
    }
    return getMarkdownFixtures().listMarkdownRegressionSamples();
  },

  debugLoadMarkdownRegressionSample: function (name) {
    if (!_IS_DEVTOOLS) {
      log.warn("Chat", "debugLoadMarkdownRegressionSample is devtools-only");
      return false;
    }
    var sample = getMarkdownFixtures().getMarkdownRegressionSample(String(name || ""));
    if (!sample) {
      log.warn("Chat", "unknown markdown regression sample: " + name);
      return false;
    }
    return this.debugReplaceMessagesWithStructuredSample(sample);
  },

  _recoverTurnFromHistory: function (options) {
    var self = this;
    var opts = options || {};
    var pending = self._pendingTurn || self._loadPendingTurn();
    if (
      !pending ||
      !pending.conversationId ||
      !pending.query ||
      pending.baselineCount === undefined
    ) {
      return Promise.resolve(false);
    }

    var maxAttempts = opts.maxAttempts || (opts.longPoll ? PENDING_TURN_POLL_MAX_ATTEMPTS : 3);
    var attempt = 0;

    function tryFetch() {
      attempt += 1;
      if (!self._isPendingTurnCurrent(pending)) {
        return Promise.resolve(false);
      }
      return api
        .getConversationMessages(pending.conversationId)
        .then(function (raw) {
          if (!self._isPendingTurnCurrent(pending)) {
            return false;
          }
          var data = api.unwrapResponse(raw) || {};
          var serverMessages = [];
          if (Array.isArray(data.messages)) {
            serverMessages = data.messages;
          } else if (Array.isArray(data)) {
            serverMessages = data;
          }
          if (
            !chatTurnRecovery.hasRecoveredAssistant(
              serverMessages,
              pending,
            )
          ) {
            if (attempt < maxAttempts) {
              return new Promise(function (resolve) {
                setTimeout(function () {
                  resolve(tryFetch());
                }, opts.longPoll ? PENDING_TURN_POLL_DELAY_MS : attempt * 700);
              });
            }
            self._finishPendingTurnRecovery(
              opts.longPoll || opts.unlockOnExhausted ? serverMessages : null,
              {
                keepPending: !!opts.keepPendingOnExhausted,
                hydrate: opts.hydrateOnExhausted !== false,
              },
            );
            return false;
          }

          self._applyHydratedConversationMessages(serverMessages, data.conversation || data);
          self._recoveringTurn = false;
          self._clearPendingTurn();
          return true;
        })
        .catch(function (err) {
          if (!self._isPendingTurnCurrent(pending)) {
            return false;
          }
          if (err && err.statusCode === 404) {
            if (wx.getStorageSync("current_session_id") === pending.conversationId) {
              self._sid = "s_" + Date.now();
              self._convId = null;
              wx.removeStorageSync("current_session_id");
              wx.removeStorageSync("current_session_ts");
            }
            self._finishPendingTurnRecovery();
            return false;
          }
          if (attempt < maxAttempts) {
            return new Promise(function (resolve) {
              setTimeout(function () {
                resolve(tryFetch());
              }, opts.longPoll ? PENDING_TURN_POLL_DELAY_MS : attempt * 700);
            });
          }
          self._finishPendingTurnRecovery(null, {
            keepPending: !!opts.keepPendingOnExhausted,
            hydrate: opts.hydrateOnExhausted !== false,
          });
          return false;
        });
    }

    return tryFetch();
  },

  _syncMessageIndexMap: function (msgs) {
    var map = Object.create(null);
    var list = Array.isArray(msgs) ? msgs : [];
    for (var i = 0; i < list.length; i++) {
      var msg = list[i];
      if (!msg || msg.id === undefined || msg.id === null) continue;
      map[msg.id] = i;
    }
    this._messageIndexMap = map;
    return map;
  },

  _flushSessionPersist: function () {
    if (this._sessionPersistTimer) {
      clearTimeout(this._sessionPersistTimer);
      this._sessionPersistTimer = null;
    }
    if (!this._sid || !this._convId) return;
    wx.setStorageSync("current_session_id", this._sid);
    wx.setStorageSync("current_session_ts", Date.now());
  },

  _scheduleSessionPersist: function (immediate) {
    if (!this._sid || !this._convId) return;
    if (immediate) {
      this._flushSessionPersist();
      return;
    }
    var self = this;
    if (this._sessionPersistTimer) {
      clearTimeout(this._sessionPersistTimer);
    }
    this._sessionPersistTimer = setTimeout(function () {
      self._sessionPersistTimer = null;
      if (!self._sid || !self._convId) return;
      wx.setStorageSync("current_session_id", self._sid);
      wx.setStorageSync("current_session_ts", Date.now());
    }, 1200);
  },

  _flushHistoryCachePersist: function () {
    if (this._historyCacheTimer) {
      clearTimeout(this._historyCacheTimer);
      this._historyCacheTimer = null;
    }
    if (!this._pendingHistoryTitle || !this._convId) {
      this._pendingHistoryTitle = "";
      return;
    }
    try {
      var cacheKey = "history_cache";
      var cached = wx.getStorageSync(cacheKey);
      if (cached && cached.groups) {
        var found = false;
        for (var i = 0; i < cached.groups.length; i++) {
          var group = cached.groups[i];
          var items = (group && group.items) || [];
          for (var j = 0; j < items.length; j++) {
            var item = items[j];
            if (item && item.id === this._convId) {
              item.title = this._pendingHistoryTitle;
              found = true;
            }
          }
        }
        if (found) wx.setStorageSync(cacheKey, cached);
      }
    } catch (_) {}
    this._pendingHistoryTitle = "";
  },

  _scheduleHistoryCachePersist: function (title) {
    if (!title || !this._convId) return;
    this._pendingHistoryTitle = title;
    var self = this;
    if (this._historyCacheTimer) {
      clearTimeout(this._historyCacheTimer);
    }
    this._historyCacheTimer = setTimeout(function () {
      self._flushHistoryCachePersist();
    }, 300);
  },

  _flushDeferredWrites: function () {
    this._flushSessionPersist();
    this._flushHistoryCachePersist();
  },

  _cancelDeferredWrites: function () {
    if (this._sessionPersistTimer) {
      clearTimeout(this._sessionPersistTimer);
      this._sessionPersistTimer = null;
    }
    if (this._historyCacheTimer) {
      clearTimeout(this._historyCacheTimer);
      this._historyCacheTimer = null;
    }
    this._pendingHistoryTitle = "";
  },

  _lazyParseBlocks: function (msgId) {
    var idx = this._find(msgId);
    if (idx === -1) return;
    var msg = this.data.messages[idx];
    // 正在流式的消息由 _flush 管理，不在此处理
    if (msg.streaming) return;
    // 已有 blocks 则跳过
    if (msg.blocks && msg.blocks.length > 0) return;
    if (msg.hasStructuredContent) return;
    // 无内容则跳过
    if (!msg.content || msg.role !== "ai") return;
    var normalized = this._buildAiMessageUpdates(idx, { parseBlocks: true });
    if (normalized) this.setData(normalized.updates);
  },

  // ── 流式控制 ──────────────────────────────────

  _stop: function (options) {
    if (options && options.cancelTurn) {
      surfaceTelemetry.trackOnce(
        "yousen:user-cancelled:" + (this._surfaceTurnId || this._sid),
        "user_cancelled",
        {
          sessionId: this._sid,
          turnId: this._surfaceTurnId || "",
        },
      );
      var streamIdx = this._streamId === null ? -1 : this._find(this._streamId);
      if (streamIdx >= 0) {
        this.setData({
          ["messages[" + streamIdx + "].thinkingStatus"]: "正在停止本轮分析…",
          ["messages[" + streamIdx + "].thinkingBadge"]: "停止中",
          ["messages[" + streamIdx + "].thinkingSub"]: "收到停止指令，正在同步本轮状态",
          ["messages[" + streamIdx + "].thinkingTone"]: "retry",
        });
      }
    }
    if (this._abort) {
      try {
        this._abort(options || {});
      } catch (_) {}
      this._abort = null;
    }
    this.setData({ canStopStream: false });
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    this._buf = "";
    if (options && options.cancelTurn) {
      this._clearPendingTurn();
      this._recoveringTurn = false;
    } else if (this._pendingTurn) {
      this._persistPendingTurn(this._pendingTurn);
    }
  },

  _onToken: function (t) {
    this._buf += t;
    if (this._flushCount === 0) {
      this._flush();
    }
    if (!this._timer) {
      var self = this;
      this._timer = setInterval(function () {
        self._flush();
      }, FLUSH_THROTTLE_MS);
    }
  },

  _shouldParseStreamingMarkdown: function (content) {
    var text = String(content || "");
    if (!text.trim()) return false;
    var interval = Math.max(1, Number(MD_PARSE_INTERVAL) || 3);
    var atParseTick = this._flushCount > 0 && this._flushCount % interval === 0;
    var endedSection = /(\n\n|[。！？.!?]\s*)$/.test(text);
    if (!atParseTick && !endedSection) return false;
    if (text.length > 24000 && this._flushCount % (interval * 2) !== 0) return false;
    return /(^|\n)(#{1,4}\s|[-*]\s|\d+[.．、]\s|\|.+\|)|\*\*|✅|❌|⚠️/.test(text);
  },

  _setAutoScrollEnabled: function (enabled) {
    this._autoScrollEnabled = !!enabled;
    if (
      !this._autoScrollEnabled &&
      (this.data.scrollToId || this.data.chatScrollWithAnimation)
    ) {
      this.setData({
        scrollToId: "",
        chatScrollWithAnimation: false,
      });
    }
  },

  _scrollChatToBottom: function (animate) {
    if (!this._autoScrollEnabled) return;
    this.setData({
      scrollToId: "msg-bottom",
      chatScrollWithAnimation: !!animate,
    });
  },

  _releaseBottomAnchor: function () {
    if (!this.data.scrollToId && !this.data.chatScrollWithAnimation) return;
    this.setData({
      scrollToId: "",
      chatScrollWithAnimation: false,
    });
  },

  _flush: function () {
    if (!this._buf || this._streamId === null) return;
    var idx = this._find(this._streamId);
    if (idx === -1) return;

    var newContent = this.data.messages[idx].content + this._buf;
    this._buf = "";
    this._flushCount++;
    var parseStreamingMarkdown = this._shouldParseStreamingMarkdown(newContent);
    var normalized = this._buildAiMessageUpdates(idx, {
      content: newContent,
      parseBlocks: parseStreamingMarkdown,
      streamLight: !parseStreamingMarkdown,
    });
    if (!normalized) return;
    if (
      !this._firstVisibleAckSent &&
      this._surfaceTurnId &&
      (
        normalized.state.renderableContent ||
        (normalized.state.blocks && normalized.state.blocks.length) ||
        (normalized.state.mcqCards && normalized.state.mcqCards.length)
      )
    ) {
      this._firstVisibleAckSent = true;
      surfaceTelemetry.trackOnce(
        "yousen:first-visible:" + this._surfaceTurnId,
        "first_visible_content_rendered",
        {
          sessionId: this._sid,
          turnId: this._surfaceTurnId,
          metadata: {
            answer_mode: this.data.answerMode,
          },
        },
      );
    }

    var update = normalized.updates;
    if (this._autoScrollEnabled) {
      update.scrollToId = "msg-bottom";
      update.chatScrollWithAnimation = false;
    }

    this.setData(update);
  },

  _onDone: function (options) {
    var wasRecoveringTurn = !!this._recoveringTurn;
    var skipHistoryRecovery = !!(options && options.skipHistoryRecovery);
    var renderedAnswer = false;
    var wasFirstAnswerPending = !!this._firstAnswerPending;
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    this._abort = null;
    if (this._buf) this._flush();

    var idx = this._find(this._streamId);
    if (idx !== -1) {
      if (this._firstAnswerPending) {
        this._firstAnswerPending = false;
        analytics.track("deeptutor_first_answer_done", {
          conversation_id: this._convId || this._sid || "",
          entry_source: this.data.entrySource,
          answer_mode: this.data.answerMode,
        });
      }
      var normalized = this._buildAiMessageUpdates(idx, { parseBlocks: true });
      if (!normalized) return;
      var state = normalized.state;
      var u = normalized.updates;
      u["messages[" + idx + "].streaming"] = false;
      renderedAnswer = !!(
        state.renderableContent ||
        (state.blocks && state.blocks.length) ||
        (state.mcqCards && state.mcqCards.length)
      );
      if (renderedAnswer && wasFirstAnswerPending) {
        trackBehavior("chat_first_answer_rendered", {
          module: "chat",
          action: "render",
          objectType: "first_answer",
          sessionId: this._convId || this._sid || "",
          turnId: this._surfaceTurnId || "",
          durationMs: this._turnStartedAtMs
            ? Math.max(0, Date.now() - this._turnStartedAtMs)
            : 0,
          result: "success",
        });
      }
      if (renderedAnswer) {
        u["messages[" + idx + "].thinkingStatus"] = "";
        u["messages[" + idx + "].thinkingBadge"] = "";
        u["messages[" + idx + "].thinkingSub"] = "";
        u["messages[" + idx + "].thinkingTone"] = "";
      }
      u.isStreaming = false;
      u.canStopStream = false;
      if (this._autoScrollEnabled) {
        u.scrollToId = "msg-bottom";
        u.chatScrollWithAnimation = false;
      } else {
        u.scrollToId = "";
        u.chatScrollWithAnimation = false;
      }
      this.setData(u);
      if (
        !this._doneRenderedAckSent &&
        this._surfaceTurnId &&
        (
          state.renderableContent ||
          (state.blocks && state.blocks.length) ||
          (state.mcqCards && state.mcqCards.length)
        )
      ) {
        this._doneRenderedAckSent = true;
        surfaceTelemetry.trackOnce(
          "yousen:done-rendered:" + this._surfaceTurnId,
          "done_rendered",
          {
            sessionId: this._sid,
            turnId: this._surfaceTurnId,
            metadata: {
              answer_mode: this.data.answerMode,
            },
          },
        );
      }
      if (this._autoScrollEnabled) {
        var self = this;
        setTimeout(function () {
          self._releaseBottomAnchor();
        }, 80);
      }
    } else {
      this.setData({ isStreaming: false, canStopStream: false });
    }
    this._streamId = null;
    this._abort = null;
    if (wasRecoveringTurn) {
      this._recoveringTurn = true;
      return;
    }
    if (!skipHistoryRecovery && !renderedAnswer && (this._pendingTurn || this._loadPendingTurn())) {
      var recoverySelf = this;
      this._recoveringTurn = true;
      this._pendingRecoveryActive = true;
      this._recoverTurnFromHistory({
        maxAttempts: PENDING_TURN_FOREGROUND_MAX_ATTEMPTS,
        unlockOnExhausted: true,
        keepPendingOnExhausted: true,
        hydrateOnExhausted: false,
      }).then(function (recovered) {
        recoverySelf._pendingRecoveryActive = false;
        if (!recovered) {
          recoverySelf._recoveringTurn = false;
          recoverySelf._continuePendingTurnRecoveryInBackground();
        }
      }, function () {
        recoverySelf._pendingRecoveryActive = false;
        recoverySelf._recoveringTurn = false;
        recoverySelf._continuePendingTurnRecoveryInBackground();
      });
      return;
    }
    this._recoveringTurn = false;
    this._clearPendingTurn();
  },

  _onError: function (m) {
    var self = this;
    var failedStreamId = this._streamId;
    this._recoveringTurn = true;
    this.setData({ canStopStream: false });
    var idx = this._find(failedStreamId);
    if (idx !== -1) {
      var msg = this.data.messages[idx];
      var state = this._buildWorkflowState(
        msg,
        {
          eventType: "progress",
          stage: "retry",
          data: "连接中断，正在同步本轮回答…",
        },
        false,
      );
      this._setWorkflowState(idx, state, false);
    }

    this._recoverTurnFromHistory().then(function (recovered) {
      if (recovered) {
        wx.showToast({ title: "已恢复本轮回答", icon: "none" });
        return;
      }

      self._recoveringTurn = false;
      var failedIdx = self._find(failedStreamId);
      if (failedIdx !== -1) {
        var failedMsg = self.data.messages[failedIdx];
        var failedState = self._buildWorkflowState(
          failedMsg,
          {
            eventType: "progress",
            stage: "retry",
            data: m || "服务异常",
          },
          false,
        );
        self._setWorkflowState(failedIdx, failedState, false);
      }
      self._onDone({ skipHistoryRecovery: true });
      self._clearPendingTurn();
      if (self._isBillingBlockedMessage(m)) {
        self._showPaywall({
          title: "需要开通后继续",
          text: "这一步会消耗 AI 答疑权益。开通后，会回到当前学习路径继续。",
        });
      }
      surfaceTelemetry.trackOnce(
        "yousen:surface-render-failed:" + (self._surfaceTurnId || self._sid),
        "surface_render_failed",
        {
          sessionId: self._sid,
          turnId: self._surfaceTurnId || "",
          metadata: {
            message: m || "服务异常",
          },
        },
      );
      wx.showToast({ title: m || "回复失败", icon: "none" });
    });
  },

  _onStatus: function (m) {
    var idx = this._find(this._streamId);
    if (idx === -1) return;
    var payload = m || {};
    var msg = this.data.messages[idx];
    var state = this._buildWorkflowState(msg, payload, true);
    this._setWorkflowState(idx, state, false);
  },

  _onStatusEnd: function () {
    var idx = this._find(this._streamId);
    if (idx === -1) return;
    var msg = this.data.messages[idx] || {};
    var summary = workflowStatus.summarizeWorkflow(msg.workflowEntries || [], false);
    var preserveThinking = !!(
      msg.renderableContent ||
      (msg.blocks && msg.blocks.length) ||
      (msg.mcqCards && msg.mcqCards.length)
    );
    this._setWorkflowState(
      idx,
      {
        entries: msg.workflowEntries || [],
        summary: summary,
      },
      preserveThinking,
    );
    if (preserveThinking) {
      this.setData({
        ["messages[" + idx + "].thinkingStatus"]: "",
        ["messages[" + idx + "].thinkingBadge"]: "",
        ["messages[" + idx + "].thinkingSub"]: "",
        ["messages[" + idx + "].thinkingTone"]: "",
      });
    }
  },

  _extractRuntimeMeta: function (d) {
    if (!d || typeof d !== "object") return null;
    var meta = {
      api_base: String(d.api_base || "").trim(),
      release_id: String(d.release_id || "").trim(),
      grading_engine_version: String(d.grading_engine_version || "").trim(),
      score_authority: String(d.score_authority || "").trim(),
      grading_rubric_provenance: String(d.grading_rubric_provenance || "").trim(),
    };
    if (Object.prototype.hasOwnProperty.call(d, "v1_case_graded")) {
      meta.v1_case_graded = d.v1_case_graded === true;
    }
    if (
      !meta.api_base &&
      !meta.release_id &&
      !meta.grading_engine_version &&
      !Object.prototype.hasOwnProperty.call(meta, "v1_case_graded")
    ) {
      return null;
    }
    return meta;
  },

  _formatRuntimeMetaText: function (meta) {
    if (!meta || typeof meta !== "object") return "";
    var parts = [];
    var apiBase = String(meta.api_base || "").trim().replace(/^https?:\/\//i, "").replace(/\/$/, "");
    if (apiBase) parts.push("API " + apiBase);
    if (meta.release_id) parts.push("release " + meta.release_id);
    if (Object.prototype.hasOwnProperty.call(meta, "v1_case_graded")) {
      parts.push(meta.v1_case_graded ? "V1 已评分" : "V1 未命中");
    }
    if (meta.grading_engine_version) parts.push(meta.grading_engine_version);
    return parts.join(" · ");
  },

  _onFinal: function (d) {
    if (!d) return;
    var idx = this._find(this._streamId);
    if (idx !== -1) {
      if (this._buf) this._flush();
      var updates = {};
      var hasVisibleAnswer = false;
      if (typeof d.response === "string" && d.response.trim()) {
        var normalized = this._buildAiMessageUpdates(idx, {
          content: d.response,
          parseBlocks: true,
        });
        if (normalized) {
          Object.assign(updates, normalized.updates);
          hasVisibleAnswer = true;
        }
      }
      if (d.citations) {
        updates["messages[" + idx + "].citations"] =
          citationFormat.formatCitations(d.citations);
      }
      if (d.next_best_action && d.next_best_action.title) {
        updates["messages[" + idx + "].nextBestAction"] = d.next_best_action;
      }
      if (d.engine) {
        updates["messages[" + idx + "].engine"] = d.engine;
      }
      if (d.engine_session_id) {
        updates["messages[" + idx + "].engineSessionId"] = d.engine_session_id;
      }
      if (d.engine_turn_id) {
        updates["messages[" + idx + "].engineTurnId"] = d.engine_turn_id;
        this._surfaceTurnId = d.engine_turn_id;
        this._updatePendingTurn({ turnId: d.engine_turn_id });
      }
      var runtimeMeta = this._extractRuntimeMeta(d);
      if (runtimeMeta) {
        updates["messages[" + idx + "].runtimeMeta"] = runtimeMeta;
        updates["messages[" + idx + "].runtimeMetaText"] =
          this._formatRuntimeMetaText(runtimeMeta);
      }
      if (d.billing && typeof d.billing === "object") {
        updates["messages[" + idx + "].billing"] = d.billing;
      }
      if (hasVisibleAnswer) {
        this._mergeVisibleAnswerSettledUpdates(idx, updates);
      }
      if (Object.keys(updates).length) {
        this.setData(updates);
      }
    }
  },

  _onPresentation: function (d) {
    if (!d || typeof d !== "object") return;
    var idx = this._find(this._streamId);
    if (idx === -1) return;
    var normalized = this._buildAiMessageUpdates(idx, {
      presentation: d,
      parseBlocks: true,
    });
    if (!normalized) return;
    var updates = normalized.updates || {};
    this._mergeVisibleAnswerSettledUpdates(idx, updates);
    this.setData(updates);
  },

  _find: function (id) {
    if (id === null) return -1;
    var map = this._messageIndexMap || Object.create(null);
    var idx = map[id];
    if (idx !== undefined) {
      var msgs = this.data.messages;
      if (msgs[idx] && msgs[idx].id === id) return idx;
    }
    var list = this.data.messages;
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        map[id] = i;
        this._messageIndexMap = map;
        return i;
      }
    }
    return -1;
  },

  _buildWorkflowState: function (msg, payload, active) {
    var entries = workflowStatus.appendWorkflowEntry(
      (msg && msg.workflowEntries) || [],
      payload,
    );
    var summary = workflowStatus.summarizeWorkflow(entries, active !== false);
    return {
      entries: entries,
      summary: summary,
    };
  },

  _setWorkflowState: function (idx, state, preserveThinking) {
    var summary = (state && state.summary) || workflowStatus.summarizeWorkflow([], false);
    var updates = {};
    updates["messages[" + idx + "].workflowEntries"] = state.entries || [];
    updates["messages[" + idx + "].workflowBadge"] = summary.badge || "";
    updates["messages[" + idx + "].workflowTitle"] = summary.headline || "";
    updates["messages[" + idx + "].workflowSub"] = summary.subline || "";
    updates["messages[" + idx + "].workflowMeta"] = summary.meta || "";
    updates["messages[" + idx + "].workflowCountText"] = summary.countText || "";
    updates["messages[" + idx + "].workflowToggleText"] = summary.toggleText || "查看处理摘要";
    updates["messages[" + idx + "].workflowTone"] = summary.tone || "analyze";
    updates["messages[" + idx + "].workflowActive"] = !!summary.active;

    if (!preserveThinking) {
      updates["messages[" + idx + "].thinkingStatus"] = summary.headline || "";
      updates["messages[" + idx + "].thinkingBadge"] = summary.badge || "";
      updates["messages[" + idx + "].thinkingSub"] = summary.subline || "";
      updates["messages[" + idx + "].thinkingTone"] = summary.tone || "analyze";
    }
    this.setData(updates);
  },

  _mergeVisibleAnswerSettledUpdates: function (idx, updates) {
    var msg = this.data.messages[idx] || {};
    var summary = workflowStatus.summarizeWorkflow(msg.workflowEntries || [], false);
    updates["messages[" + idx + "].streaming"] = false;
    updates["messages[" + idx + "].workflowBadge"] = summary.badge || "";
    updates["messages[" + idx + "].workflowTitle"] = summary.headline || "";
    updates["messages[" + idx + "].workflowSub"] = summary.subline || "";
    updates["messages[" + idx + "].workflowMeta"] = summary.meta || "";
    updates["messages[" + idx + "].workflowCountText"] = summary.countText || "";
    updates["messages[" + idx + "].workflowToggleText"] =
      summary.toggleText || "查看处理摘要";
    updates["messages[" + idx + "].workflowTone"] = summary.tone || "compose";
    updates["messages[" + idx + "].workflowActive"] = false;
    updates["messages[" + idx + "].thinkingStatus"] = "";
    updates["messages[" + idx + "].thinkingBadge"] = "";
    updates["messages[" + idx + "].thinkingSub"] = "";
    updates["messages[" + idx + "].thinkingTone"] = "";
    updates.isStreaming = false;
    updates.canStopStream = false;
  },

  _buildAiMessageUpdates: function (idx, opts) {
    var msg = this.data.messages[idx];
    if (!msg || msg.role !== "ai") return null;
    var options = opts || {};
    var hasContent = Object.prototype.hasOwnProperty.call(options, "content");
    var hasPresentation = Object.prototype.hasOwnProperty.call(options, "presentation");
    var streamLight = !!options.streamLight && !hasPresentation && !msg.presentation;
    var content = aiMessageState.coerceUserVisibleContent(
      hasContent ? String(options.content || "") : String(msg.content || ""),
    );
    if (streamLight) {
      var lightUpdates = {};
      if (hasContent) {
        lightUpdates["messages[" + idx + "].content"] = content;
      }
      lightUpdates["messages[" + idx + "].renderableContent"] = content;
      return {
        updates: lightUpdates,
        state: {
          renderableContent: content,
          blocks: msg.blocks || [],
          mcqCards: msg.mcqCards || null,
          hasStructuredContent: !!msg.hasStructuredContent,
        },
      };
    }
    var presentation = aiMessageState.sanitizePresentationForState
      ? aiMessageState.sanitizePresentationForState(
          hasPresentation ? options.presentation || null : msg.presentation || null,
        )
      : hasPresentation
        ? options.presentation || null
        : msg.presentation || null;
    var state = aiMessageState.deriveAiMessageRenderState({
      content: content,
      presentation: presentation,
      parseBlocks: !!options.parseBlocks,
    });
    var updates = {};
    if (hasContent) {
      updates["messages[" + idx + "].content"] = content;
    }
    if (hasPresentation) {
      updates["messages[" + idx + "].presentation"] = presentation;
    }
    updates["messages[" + idx + "].renderableContent"] = state.renderableContent;
    updates["messages[" + idx + "].mcqCards"] = state.mcqCards;
    updates["messages[" + idx + "].mcqHint"] = state.mcqHint;
    updates["messages[" + idx + "].mcqReceipt"] = state.mcqReceipt;
    updates["messages[" + idx + "].mcqInteractiveReady"] = state.mcqInteractiveReady;
    updates["messages[" + idx + "].mcqReviewMode"] = state.mcqReviewMode;
    updates["messages[" + idx + "].originalContent"] = state.originalContent || "";
    updates["messages[" + idx + "].originalExpanded"] = state.originalCollapsed === false;
    updates["messages[" + idx + "].hasStructuredContent"] = !!state.hasStructuredContent;
    if (options.parseBlocks || state.hasStructuredContent) {
      updates["messages[" + idx + "].blocks"] = state.blocks || [];
    }
    return {
      updates: updates,
      state: state,
    };
  },

  _selectedMcqKeys: function (card) {
    if (!card || !Array.isArray(card.options)) return [];
    var keys = [];
    for (var i = 0; i < card.options.length; i++) {
      if (card.options[i] && card.options[i].selected)
        keys.push(card.options[i].key);
    }
    return keys.sort();
  },

  _buildFallbackMcqJudgePrompt: function (cards, selections) {
    var items = Array.isArray(cards) ? cards : [];
    if (!items.length || !Array.isArray(selections) || !selections.length) return "";

    var questionBlocks = [];
    for (var i = 0; i < items.length; i++) {
      var card = items[i];
      if (!card) continue;
      var selectedKeys = this._selectedMcqKeys(card);
      if (!selectedKeys.length) continue;

      var lines = [];
      lines.push("第" + (card.index || i + 1) + "题：");
      lines.push(card.stem || "请选择正确选项");

      var opts = Array.isArray(card.options) ? card.options : [];
      for (var j = 0; j < opts.length; j++) {
        var opt = opts[j];
        if (!opt || !opt.key) continue;
        lines.push(String(opt.key).toUpperCase() + ". " + (opt.text || ""));
      }

      lines.push("我的答案：" + selectedKeys.join("、"));
      questionBlocks.push(lines.join("\n"));
    }

    if (!questionBlocks.length) return "";
    if (questionBlocks.length === 1) {
      return (
        "请根据你刚才出的这道选择题，判断我选得对不对，并给出正确答案与简明解析。\n\n" +
        questionBlocks[0]
      );
    }

    return (
      "请根据你刚才出的这些选择题，逐题判断我选得对不对，并按“第N题：是否正确 / 正确答案 / 简明解析”的格式回复。\n\n" +
      questionBlocks.join("\n\n")
    );
  },

  _buildVisibleCardFollowupContext: function (card, userAnswer) {
    var source = card || {};
    var optionMap = {};
    var options = Array.isArray(source.options) ? source.options : [];
    for (var i = 0; i < options.length; i++) {
      var option = options[i] || {};
      var key = String(option.key || "").trim().toUpperCase();
      var text = String(option.text || option.value || "").trim();
      if (key && text) optionMap[key] = text;
    }
    var context = {
      question_id: String(
        source.questionId ||
          (source.followupContext && source.followupContext.question_id) ||
          "",
      ).trim(),
      question: String(source.stem || "").trim(),
      question_type: source.questionType || "choice",
      options: optionMap,
      user_answer: String(userAnswer || "").trim(),
    };
    if (!context.question && !context.question_id && !Object.keys(optionMap).length) {
      return null;
    }
    return context;
  },

  _buildMcqSubmitPayload: function (cards) {
    var selections = [];
    var structuredQuestions = [];
    var structuredAnswers = [];
    var missingContext = false;
    var items = Array.isArray(cards) ? cards : [];
    for (var i = 0; i < items.length; i++) {
      var card = items[i];
      if (!card) continue;
      var keys = this._selectedMcqKeys(card);
      var optionMap = {};
      var opts = Array.isArray(card.options) ? card.options : [];
      for (var j = 0; j < opts.length; j++) {
        if (opts[j] && opts[j].key) optionMap[opts[j].key] = opts[j].text || "";
      }
      structuredQuestions.push({
        question_number: card.index || i + 1,
        question_id: String(
          card.questionId ||
            (card.followupContext && card.followupContext.question_id) ||
            "",
        ).trim(),
        stem: card.stem || "",
        hint: card.hint || "",
        options: optionMap,
        question_type: card.questionType || "single_choice",
        selected_answer: keys.length ? keys.join("") : "",
      });
      if (keys.length) {
        selections.push({
          index: card.index || i + 1,
          keys: keys,
          questionType: card.questionType || "single_choice",
        });
        structuredAnswers.push({
          question_number: card.index || i + 1,
          question_id: String(
            card.questionId ||
              (card.followupContext && card.followupContext.question_id) ||
              "",
          ).trim(),
          selected_answer: keys.join(""),
          question_type: card.questionType || "single_choice",
        });
        if (!card.followupContext || typeof card.followupContext !== "object") {
          missingContext = true;
        }
      }
    }
    if (!selections.length) return null;
    var rows = [];
    for (var k = 0; k < selections.length; k++) {
      rows.push("第" + selections[k].index + "题：" + selections[k].keys.join("、"));
    }
    var followupQuestionContext = null;
    if (selections.length === 1) {
      for (var m = 0; m < items.length; m++) {
        var singleCard = items[m];
        if (!singleCard) continue;
        if (Number(singleCard.index) !== Number(selections[0].index)) continue;
        var singleUserAnswer = selections[0].keys.join("");
        var visibleSingleContext = this._buildVisibleCardFollowupContext(singleCard, singleUserAnswer);
        followupQuestionContext = Object.assign({}, visibleSingleContext || {}, singleCard.followupContext || {}, {
          user_answer: selections[0].keys.join(""),
        });
        if (!followupQuestionContext.question && !followupQuestionContext.question_id) {
          followupQuestionContext = null;
        }
        break;
      }
    } else {
      var compositeItems = [];
      var questionLines = [];
      for (var n = 0; n < items.length; n++) {
        var compositeCard = items[n];
        if (!compositeCard) continue;
        var compositeUserAnswer = this._selectedMcqKeys(compositeCard).join("");
        var visibleCompositeContext = this._buildVisibleCardFollowupContext(
          compositeCard,
          compositeUserAnswer,
        );
        var compositeContext = Object.assign(
          {},
          visibleCompositeContext || {},
          compositeCard.followupContext || {},
          {
            user_answer: compositeUserAnswer,
          },
        );
        if (!compositeContext.question && !compositeContext.question_id) continue;
        compositeItems.push(
          compositeContext,
        );
        questionLines.push(
          "第" +
            (compositeCard.index || n + 1) +
            "题：\n" +
            (compositeCard.stem || "请选择正确选项"),
        );
      }
      if (compositeItems.length) {
        followupQuestionContext = {
          question_id: "question_set",
          question: questionLines.join("\n\n"),
          question_type: "choice",
          items: compositeItems,
        };
      }
    }
    var text =
      selections.length === 1 && followupQuestionContext
        ? "我选" + selections[0].keys.join("、")
        : rows.join("；");
    if (missingContext && !followupQuestionContext) {
      return {
        text: this._buildFallbackMcqJudgePrompt(items, selections),
        structuredSubmitContext: {
          questions: structuredQuestions,
          answers: structuredAnswers,
        },
        followupQuestionContext: null,
      };
    }
    return {
      text: text,
      structuredSubmitContext: {
        questions: structuredQuestions,
        answers: structuredAnswers,
      },
      followupQuestionContext: followupQuestionContext,
    };
  },

  // ── 仪表盘 ─────────────────────────────────────

  _loadDashboard: function () {
    var self = this;
    var cachedDashboard = readCachedHomeDashboard();
    if (cachedDashboard) {
      self.setData(buildHomeDashboardUpdate(cachedDashboard));
    }
    return api
      .getHomeDashboard()
      .then(function (resp) {
        var d = unwrap(resp) || {};
        writeCachedHomeDashboard(d);
        self.setData(buildHomeDashboardUpdate(d));
      })
      .catch(function (err) {
        log.warn("Dashboard", "API failed: " + ((err && err.message) || err));
        if (cachedDashboard) return;
        // No trusted canonical focus: keep only static examples.
        self.setData({
          focusTone: "plan",
          focusTitle: "",
          focusMeta: "",
          focusText: "",
          focusPromptIntent: null,
          focusActionType: "",
          recommendedPrompts: [],
          showStaticExamples: true,
          focusQuery: "",
        });
      });
  },

  onFocusTap: function () {
    if (this.data.isGuestPreview) {
      this._showLoginGate("");
      return;
    }
    if (this.data.focusActionType === "assessment") {
      if (!flags.ensureFeatureEnabled("assessment", { redirect: false })) return;
      wx.navigateTo({ url: route.assessment() });
      return;
    }
    var query = this.data.focusQuery;
    if (query && !this.data.isStreaming) {
      this._send(query, { promptIntent: this.data.focusPromptIntent });
    }
  },

  onRecommendedPromptTap: function (e) {
    if (this.data.isStreaming) return;
    var index = Number(e && e.currentTarget && e.currentTarget.dataset.index);
    var prompt = (this.data.recommendedPrompts || [])[index];
    if (!prompt || !prompt.text) return;
    helpers.vibrate("light");
    if (this.data.isGuestPreview) {
      this._showLoginGate(prompt.text, { promptIntent: prompt.promptIntent });
      return;
    }
    this._send(prompt.text, { promptIntent: prompt.promptIntent });
  },

  onNextBestActionTap: function (e) {
    if (this.data.isStreaming) return;
    var idx = this._find(e.currentTarget.dataset.msgid);
    if (idx === -1) return;
    var nba = this.data.messages[idx] && this.data.messages[idx].nextBestAction;
    if (!nba || !nba.title) return;
    helpers.vibrate("light");
    var query = String(nba.query || "").trim();
    if (!query) {
      var target = String(nba.target || nba.title || "").slice(0, 80);
      if (!target) return;
      query = "针对我的薄弱点出一道练习题：" + target + "。出题后等我作答再批改。";
    }
    this._send(query);
  },

  // ── Hero 弹性拖拽 + 震动 ───────────────────────
  _onHeroDragStart: function (e) {
    if (helpers.isLowEnd && helpers.isLowEnd()) return;
    this._dragStartY = e.touches[0].clientY;
    this._dragVibrated = false;
    this.setData({ _heroDragTransition: "none" });
  },
  _onHeroDragMove: function (e) {
    var self = this;
    if (!this._dragStartY) return;
    var delta = e.touches[0].clientY - this._dragStartY;
    // 阻尼系数：拖得越远阻力越大
    var damped =
      delta > 0
        ? Math.min(HERO_MAX_DRAG_PX, delta * HERO_DRAG_DAMPING)
        : Math.max(-HERO_MAX_DRAG_PX, delta * HERO_DRAG_DAMPING);
    this._heroDragNextY = damped;
    if (!this._heroDragFramePending) {
      this._heroDragFramePending = true;
      wx.nextTick(function () {
        self._heroDragFramePending = false;
        self.setData({ _heroDragY: self._heroDragNextY || 0 });
      });
    }
    // 超过阈值时震动一次
    if (!this._dragVibrated && Math.abs(damped) > HERO_VIBRATE_THRESHOLD_PX) {
      this._dragVibrated = true;
      helpers.vibrate("light");
    }
  },
  _onHeroDragEnd: function () {
    if (!this._dragStartY) return;
    this._dragStartY = null;
    this._heroDragFramePending = false;
    this._heroDragNextY = 0;
    // 弹簧回弹动画
    this.setData({
      _heroDragTransition: "transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)",
      _heroDragY: 0,
    });
    // 动画结束后清除 transition，避免影响下次拖拽
    var self = this;
    setTimeout(function () {
      self.setData({ _heroDragTransition: "none" });
    }, 520);
  },

  // ── 交互 ──────────────────────────────────────

  onInput: function (e) {
    var self = this;
    self._inputText = e.detail.value;
    if (self._inputTimer) clearTimeout(self._inputTimer);
    self._inputTimer = setTimeout(function () {
      self.setData({ inputText: self._inputText });
    }, INPUT_DEBOUNCE_MS);
  },

  onMode: function (e) {
    helpers.vibrate("light");
    var nextMode = e.currentTarget.dataset.m;
    this.setData({ answerMode: nextMode, enableReason: false });
  },

  onToggleWebSearch: function () {
    helpers.vibrate("light");
    if (!this._isWebSearchAvailable()) {
      this._saveToolPrefs(false, false);
      this.setData({ enableReason: false, enableWebSearch: false });
      wx.showToast({ title: "联网暂不可用", icon: "none", duration: 1800 });
      return;
    }
    var nextWebSearch = !this.data.enableWebSearch;
    this._saveToolPrefs(false, nextWebSearch);
    this.setData({ enableReason: false, enableWebSearch: nextWebSearch });
    wx.showToast({
      title: nextWebSearch ? "本轮可联网" : "已关闭联网",
      icon: "none",
      duration: 1400,
    });
  },

  _saveToolPrefs: function (enableReason, enableWebSearch) {
    wx.setStorageSync(CHAT_TOOL_PREFS_KEY, {
      enableReason: false,
      enableWebSearch: this._isWebSearchAvailable() && !!enableWebSearch,
    });
  },

  _isWebSearchAvailable: function () {
    return this.data.webSearchAvailable === true;
  },

  _loadToolRuntimeCapabilities: function (savedToolPrefs) {
    var self = this;
    if (!api || typeof api.getRuntimeCapabilities !== "function") return;
    api
      .getRuntimeCapabilities()
      .then(function (res) {
        var body = unwrap(res) || {};
        var tools = body.tools && typeof body.tools === "object" ? body.tools : {};
        var webSearch = tools.web_search || {};
        var available = webSearch.available === true;
        self.setData({
          webSearchAvailable: available,
          enableWebSearch: available && !!(savedToolPrefs && savedToolPrefs.enableWebSearch),
        });
        if (available && savedToolPrefs && savedToolPrefs.enableWebSearch) {
          self._saveToolPrefs(false, true);
        } else if (!available && savedToolPrefs && savedToolPrefs.enableWebSearch) {
          self._saveToolPrefs(false, false);
        }
      })
      .catch(function () {
        self.setData({
          webSearchAvailable: DEFAULT_WEB_SEARCH_AVAILABLE,
          enableWebSearch: false,
        });
      });
  },

  _shouldAutoEnableWebSearch: function (query) {
    return false;
  },

  _getSelectedTools: function (query) {
    var tools = [];
    if (this._isWebSearchAvailable() && (this.data.enableWebSearch || this._shouldAutoEnableWebSearch(query))) {
      tools.push("web_search");
    }
    return tools;
  },

  _buildTutorInteraction: function () {
    var mode = String(this.data.answerMode || "AUTO").toUpperCase();
    return {
      profile: "tutorbot",
      hints: {
        product_surface: "wechat_miniprogram",
        entry_role: "tutorbot",
        subject_domain: "construction_exam",
        requested_response_mode:
          mode === "FAST" ? "fast" : mode === "DEEP" ? "deep" : "smart",
      },
    };
  },

  _applySelectedToolHints: function (interaction, tools) {
    if (tools.indexOf("web_search") === -1) return interaction;
    interaction.hints = Object.assign({}, interaction.hints || {}, {
      current_info_required: true,
    });
    return interaction;
  },

  // ── 对话滚动：上滑显示 tab bar，下滑隐藏 ─────
  _onChatScroll: function (e) {
    var y = e.detail.scrollTop;
    var lastY = this._lastScrollY || 0;
    this._lastScrollY = y;
    if (y < lastY - 8 && this._autoScrollEnabled) {
      this._setAutoScrollEnabled(false);
    }
    var now = Date.now();
    if (
      this._scrollToggleTime &&
      now - this._scrollToggleTime < SCROLL_TOGGLE_COOLDOWN_MS
    )
      return;
    var tab = helpers.getWorkspaceShell(this);
    if (!tab) return;
    if (y < lastY - 5) {
      // 上滑（往回看历史）→ 显示 tab bar
      if (tab.data.hidden) {
        if (flags.shouldShowWorkspaceShell()) {
          this._setWorkspaceShellHidden(false);
          this._scrollToggleTime = now;
        }
      }
    } else if (y > lastY + 5) {
      // 下滑（看最新消息）→ 隐藏 tab bar
      if (!tab.data.hidden) {
        this._setWorkspaceShellHidden(true);
        this._scrollToggleTime = now;
      }
    }
  },

  _onChatScrollToLower: function () {
    if (!this._autoScrollEnabled) {
      this._setAutoScrollEnabled(true);
      if (this.data.isStreaming) {
        this._scrollChatToBottom(false);
      }
    }
  },

  sendMessage: function () {
    if (!runtime.isNetworkAvailable()) {
      wx.showToast({ title: "当前无网络连接", icon: "none", duration: 2000 });
      return;
    }
    var text = (this._inputText || this.data.inputText || "").trim();
    if (!text || this.data.canStopStream) return;
    helpers.vibrate("medium");
    this._inputText = "";
    this.setData({ inputText: "" });
    this._send(text);
  },

  sendExample: function (e) {
    if (this.data.canStopStream) return;
    helpers.vibrate("light");
    if (this.data.isGuestPreview) {
      this._showLoginGate(e.currentTarget.dataset.text);
      return;
    }
    this._send(e.currentTarget.dataset.text);
  },

  stopStream: function () {
    helpers.vibrate("light");
    this._stop({ cancelTurn: true });
  },

  _send: function (query, extraOpts) {
    var self = this;
    var startSend = function () {
      if (self._convId && !self._sid) {
        self._sid = self._convId;
        self._scheduleSessionPersist(true);
      }
      self._doSend(query, extraOpts);
    };

    if (!runtime.isNetworkAvailable()) {
      wx.showToast({ title: "当前无网络连接", icon: "none", duration: 2000 });
      return;
    }
    self._releaseStalePendingRecoveryForManualSend();
    if (self.data.isStreaming) return;
    self._stop();

    var canSendWithAuth =
      typeof auth.isLoggedIn === "function" ? auth.isLoggedIn() : !!auth.getToken();
    if (!canSendWithAuth) {
      self._showLoginGate(query, extraOpts);
      return;
    }

    startSend();
  },

  _doSend: function (query, extraOpts) {
    var self = this;
    var sendOptions = extraOpts && typeof extraOpts === "object" ? extraOpts : {};
    // 教学卡入口上下文：并入既有 promptIntent 载体随首问发出（一次性，发完即清），
    // 不与显式传入的 promptIntent（如摸底错题训练）竞争。
    if (self._teachEntryIntent && !sendOptions.promptIntent) {
      sendOptions.promptIntent = self._teachEntryIntent;
      self._teachEntryIntent = null;
    }
    var reuseUserMessage = !!sendOptions.reuseUserMessage;
    var autoWebSearch =
      self._isWebSearchAvailable() && !self.data.enableWebSearch && self._shouldAutoEnableWebSearch(query);
    var selectedTools = self._getSelectedTools(query);

    if (!self._sid && self._convId) {
      self._sid = self._convId;
    }
    var candidateSessionId = String(self._convId || self._sid || "").trim();
    var streamSessionId = isLocalDraftSessionId(candidateSessionId) ? "" : candidateSessionId;

    // 每次发消息只做低频续期，避免把同步落盘放到高频流式路径里
    if (streamSessionId) {
      self._scheduleSessionPersist(false);
    }

    var userMsg = { id: "u" + self._counter++, role: "user", content: query };
    if (sendOptions.followupQuestionContext && typeof sendOptions.followupQuestionContext === "object") {
      userMsg.followupQuestionContext = sendOptions.followupQuestionContext;
    }
    if (sendOptions.structuredSubmitContext && typeof sendOptions.structuredSubmitContext === "object") {
      userMsg.structuredSubmitContext = sendOptions.structuredSubmitContext;
    }
    if (sendOptions.promptIntent && typeof sendOptions.promptIntent === "object") {
      userMsg.promptIntent = sendOptions.promptIntent;
    }
    var aiMsg = {
      id: "a" + self._counter++,
      role: "ai",
      content: "",
      renderableContent: "",
      streaming: true,
      blocks: [],
      hasStructuredContent: false,
      presentation: null,
      mcqCards: null,
      mcqHint: "",
      mcqReceipt: "",
      mcqInteractiveReady: false,
      mcqReviewMode: false,
      originalContent: "",
      originalExpanded: false,
      thinkingStatus: "鲁班正在按采分点琢磨…",
      thinkingBadge: "",
      thinkingSub: "",
      thinkingTone: "",
      workflowEntries: [],
      workflowExpanded: false,
      workflowBadge: "",
      workflowTitle: "",
      workflowSub: "",
      workflowMeta: "",
      workflowCountText: "",
      workflowToggleText: "查看处理摘要",
      workflowTone: "analyze",
      workflowActive: true,
      citations: null,
      engine: "deeptutor",
      engineSessionId: "",
      engineTurnId: "",
      runtimeMeta: null,
      runtimeMetaText: "",
      billing: null,
      feedback: "",
    };
    self._streamId = aiMsg.id;
    self._buf = "";
    self._flushCount = 0;
    self._autoScrollEnabled = true;

    var existing = self.data.messages;
    var inferTitleOnStart = existing.length === 0;
    var messageReserve = reuseUserMessage ? 1 : 2;
    if (existing.length > MAX_MESSAGES - messageReserve) {
      existing = existing.slice(existing.length - (MAX_MESSAGES - messageReserve));
    }
    var msgs = reuseUserMessage ? existing.concat([aiMsg]) : existing.concat([userMsg, aiMsg]);
    // 同一轮消息在网络重连时复用同一个客户端侧标识。
    var _turnId =
      self._sid +
      "_" +
      Date.now().toString(36) +
      "_" +
      Math.random().toString(36).substr(2, 4);
    var pendingDraft = {
      baselineCount: existing.length,
      query: query,
      clientTurnId: _turnId,
      createdAt: Date.now(),
    };
    if (streamSessionId) {
      self._persistPendingTurn({
        conversationId: streamSessionId,
        baselineCount: pendingDraft.baselineCount,
        query: pendingDraft.query,
        clientTurnId: pendingDraft.clientTurnId,
        createdAt: pendingDraft.createdAt,
      });
    }
    self._syncMessageIndexMap(msgs);
    if (inferTitleOnStart) {
      analytics.track("deeptutor_first_question_start", {
        conversation_id: self._convId || self._sid || _turnId,
        entry_source: self.data.entrySource,
        answer_mode: self.data.answerMode,
      });
    }
    self._firstAnswerPending = !!(self._firstAnswerPending || inferTitleOnStart);

    self.setData({
      messages: msgs,
      hasMessages: true,
      isStreaming: true,
      canStopStream: true,
      scrollToId: "msg-bottom",
      chatScrollWithAnimation: false,
      // 10d 带入条：本轮携带上下文时可见化；无新上下文时保留会话内已有条
      contextBanner:
        buildContextBannerLabel(
          sendOptions.followupQuestionContext,
          sendOptions.promptIntent,
        ) ||
        self.data.contextBanner ||
        "",
    });
    self._syncWorkspaceChrome({ hasMessages: true });
    // 建立 IntersectionObserver 懒解析（延迟一帧确保 DOM 已渲染）
    var setupSelf = self;
    setTimeout(function () {
      setupSelf._setupObserver();
    }, 50);
    var tutorInteraction = self._applySelectedToolHints(self._buildTutorInteraction(), selectedTools);
    self._surfaceTurnId = "";
    self._firstVisibleAckSent = false;
    self._doneRenderedAckSent = false;
    self._turnStartedAtMs = Date.now();
    surfaceTelemetry.track("start_turn_sent", {
      sessionId: streamSessionId || _turnId,
      metadata: {
        answer_mode: self.data.answerMode,
        tools_count: selectedTools.length,
      },
    });
    trackBehavior("chat_message_sent", {
      module: "chat",
      action: "send",
      sessionId: streamSessionId || _turnId,
      turnId: _turnId,
      entrySource: self.data.entrySource || "",
      result: "accepted",
    });
    self._abort = wsStream.streamChat(
      {
        query: query,
        sessionId: streamSessionId,
        mode: self.data.answerMode,
        tools: selectedTools,
        config: { bot_id: "construction-exam-coach" },
        interactionProfile: tutorInteraction.profile,
        interactionHints: tutorInteraction.hints,
        clientTurnId: _turnId,
        structuredSubmitContext: extraOpts && extraOpts.structuredSubmitContext,
        followupQuestionContext: extraOpts && extraOpts.followupQuestionContext,
        promptIntent: sendOptions.promptIntent,
        capability: resolveAssessmentTrainingCapability(sendOptions.promptIntent),
        persistUserMessage: sendOptions.persistUserMessage,
        inferTitleOnStart: inferTitleOnStart,
      },
      {
        onStarted: function (payload) {
          var started = payload && typeof payload === "object" ? payload : {};
          var conversation = started.conversation && typeof started.conversation === "object"
            ? started.conversation
            : {};
          var turn = started.turn && typeof started.turn === "object" ? started.turn : {};
          var startedSessionId = String(started.sessionId || conversation.id || "").trim();
          var startedTurnId = String(started.turnId || turn.id || "").trim();
          if (startedSessionId) {
            self._convId = startedSessionId;
            self._sid = startedSessionId;
            self._scheduleSessionPersist(true);
            self._persistPendingTurn(
              Object.assign({}, pendingDraft, {
                conversationId: startedSessionId,
                turnId: startedTurnId,
              })
            );
          }
          if (startedTurnId) {
            self._surfaceTurnId = startedTurnId;
            self._updatePendingTurn({ turnId: startedTurnId });
          }
        },
        onToken: function (t) {
          self._onToken(t);
        },
        onDone: function () {
          self._onDone();
        },
        onError: function (m) {
          self._onError(m);
        },
        onStatus: function (m) {
          self._onStatus(m);
        },
        onStatusEnd: function () {
          self._onStatusEnd();
        },
        onThinkingHeader: function (m) {
          self._onStatus(m);
        },
        onFinal: function (d) {
          self._onFinal(d);
        },
        onPresentation: function (d) {
          self._onPresentation(d);
        },
        onTelemetryEvent: function (event) {
          if (!event || !event.eventName) return;
          if (event.turnId) {
            self._surfaceTurnId = event.turnId;
            self._updatePendingTurn({ turnId: event.turnId });
          }
          if (event.eventName === "resume_succeeded") {
            surfaceTelemetry.trackOnce(
              "yousen:resume-succeeded:" + (event.turnId || self._sid),
              event.eventName,
              {
                sessionId: event.sessionId || self._sid,
                turnId: event.turnId || "",
                metadata: event.metadata || {},
              },
            );
            return;
          }
          surfaceTelemetry.track(event.eventName, {
            sessionId: event.sessionId || self._sid,
            turnId: event.turnId || "",
            metadata: event.metadata || {},
          });
        },
        onUpdatedTitle: function (title) {
          // [FIX 2026-04-01] 服务端流式推送会话标题 → 同步更新 history 缓存
          if (!title) return;
          self._scheduleHistoryCachePersist(title);
        },
        onResult: function () {},
        onWorkflowStep: function () {},
        onWorkflowStepDone: function () {},
      },
    );
  },

  _restoreConversation: function (convId) {
    var self = this;
    if (isLocalDraftSessionId(convId)) {
      self._convId = null;
      if (!self._sid || !isLocalDraftSessionId(self._sid)) {
        self._sid = "s_" + Date.now();
      }
      self._clearPendingTurn();
      wx.removeStorageSync("current_session_id");
      wx.removeStorageSync("current_session_ts");
      if (!self.data.messages.length) {
        self.setData({ hasMessages: false, isStreaming: false });
        self._syncWorkspaceChrome({ hasMessages: false });
      }
      return;
    }
    self._convId = convId;
    self._sid = convId;
    // [FIX-SESSION-3] 恢复历史对话时同步持久化（含时间戳）
    self._scheduleSessionPersist(true);
    api
      .getConversationMessages(convId)
      .then(function (raw) {
        var data = api.unwrapResponse(raw);
        self._applyHydratedConversationMessages(
          data.messages || data || [],
          data.conversation || data,
        );
      })
      .catch(function (err) {
        if (err && err.statusCode === 404) {
          if (wx.getStorageSync("current_session_id") === convId) {
            wx.removeStorageSync("current_session_id");
            wx.removeStorageSync("current_session_ts");
          }
          self._convId = null;
          self._sid = "s_" + Date.now();
        }
        if (!self.data.messages.length) {
          self.setData({ hasMessages: false });
          self._syncWorkspaceChrome({ hasMessages: false });
        }
        wx.showToast({ title: "加载对话失败", icon: "none" });
      });
  },

  _checkDiagnostic: function () {
    if (!flags.isFeatureEnabled("assessment")) return;
    // 已做过或已跳过则不弹
    if (wx.getStorageSync("diagnostic_completed")) return;
    if (wx.getStorageSync("diagnostic_skipped")) return;
    // 只在 Hero 主页弹出
    if (this.data.hasMessages) return;
    function showDiagnosticModal() {
      trackBehavior("section_viewed", {
        module: "assessment",
        section: "entry_modal",
        action: "view",
        entrySource: "chat_home",
      });
      wx.showModal({
        title: "欢迎新同学",
        content:
          "建议先做一次摸底测试（约 8 分钟），AI 会根据你的水平定制学习内容。",
        confirmText: "开始测试",
        cancelText: "稍后再说",
        success: function (res) {
          trackBehavior("assessment_prompt_result", {
            module: "assessment",
            section: "entry_modal",
            action: res.confirm ? "start_probe" : "dismiss",
            result: res.confirm ? "start" : "later",
            entrySource: "chat_home",
          });
          if (res.confirm) {
            wx.navigateTo({ url: route.assessment() });
          } else {
            wx.setStorageSync("diagnostic_skipped", true);
          }
        },
      });
    }

    return api
      .getAssessmentProfile()
      .then(function (raw) {
        if (hasAssessmentSignal(raw)) {
          wx.setStorageSync("diagnostic_completed", true);
          return;
        }
        showDiagnosticModal();
      })
      .catch(function () {
        showDiagnosticModal();
      });
  },

  clearMessages: function () {
    this._stop();
    this._teardownObserver();
    this._autoScrollEnabled = true;
    this.setData({
      messages: [],
      hasMessages: false,
      isStreaming: false,
      canStopStream: false,
      scrollToId: "",
      chatScrollWithAnimation: false,
      contextBanner: "",
      inputPlaceholder: "直接问建筑实务：考点、真题、规范、错题",
    });
    this._teachEntryIntent = null;
    this._syncWorkspaceChrome({ hasMessages: false });
    this._cancelDeferredWrites();
    this._sid = "s_" + Date.now();
    this._convId = null;
    this._streamId = null;
    this._firstAnswerPending = false;
    this._messageIndexMap = Object.create(null);
    // [FIX-SESSION-4] 用户主动清除对话时清除持久化
    wx.removeStorageSync("current_session_id");
    wx.removeStorageSync("current_session_ts");
    // 回到 Hero 首页时恢复 tab bar
    var shell = helpers.getWorkspaceShell(this);
    if (shell) {
      this._setWorkspaceShellHidden(!this._shouldShowWorkspaceShell());
    }
  },

  onMcqTap: function (e) {
    if (this.data.isStreaming) return;
    var idx = this._find(e.currentTarget.dataset.msgid);
    if (idx === -1) return;
    if (!this.data.messages[idx].mcqInteractiveReady) return;
    helpers.vibrate("medium");
    var key = String(e.currentTarget.dataset.key || "").toUpperCase();
    var qindex = Number(e.currentTarget.dataset.qindex || 0);
    var cards = this.data.messages[idx].mcqCards || [];
    var nextCards = [];
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var nextOptions = [];
      var isTargetCard = Number(card.index) === qindex;
      for (var j = 0; j < (card.options || []).length; j++) {
        var option = card.options[j];
        var selected = !!option.selected;
        if (isTargetCard) {
          if (card.questionType === "multi_choice") {
            if (option.key === key) selected = !selected;
          } else {
            selected = option.key === key;
          }
        }
        nextOptions.push({
          key: option.key,
          text: option.text,
          selected: selected,
        });
      }
      nextCards.push({
        index: card.index,
        stem: card.stem,
        hint: card.hint,
        questionType: card.questionType,
        options: nextOptions,
        followupContext: card.followupContext || null,
        questionId: card.questionId || "",
        hasContext: !!card.hasContext,
      });
    }
    this.setData({ ["messages[" + idx + "].mcqCards"]: nextCards });
  },

  onMcqSubmit: function (e) {
    if (this.data.isStreaming) return;
    var idx = this._find(e.currentTarget.dataset.msgid);
    if (idx === -1) return;
    var msg = this.data.messages[idx];
    if (!msg.mcqInteractiveReady) {
      wx.showToast({
        title: "当前题卡仅供查看，请让 AI 重新出题后再作答",
        icon: "none",
      });
      return;
    }
    var payload = this._buildMcqSubmitPayload(msg.mcqCards || []);
    if (!payload) {
      wx.showToast({ title: "请先选择答案", icon: "none" });
      return;
    }
    helpers.vibrate("medium");
    if (msg.mcqReceipt && payload.structuredSubmitContext) {
      var questions = payload.structuredSubmitContext.questions || [];
      for (var i = 0; i < questions.length; i++) {
        questions[i].receipt = msg.mcqReceipt;
      }
    }
    if (this._activeAssessmentTrainingIntent && payload.structuredSubmitContext) {
      payload.promptIntent = Object.assign({}, this._activeAssessmentTrainingIntent, {
        learning_signal_type: "training_completed",
        completed_question_count: (payload.structuredSubmitContext.answers || []).length,
      });
    }
    this._send(payload.text, payload);
  },

  goHome: function () {
    // chat 页本身就是主页，点 logo 回到 Hero 状态
    runtime.clearWorkspaceBack();
    this.setData({
      workspaceBackVisible: false,
      workspaceBackLabel: "返回",
    });
    this.clearMessages();
  },

  goYousenHome: function () {
    helpers.vibrate("light");
    runtime.clearWorkspaceBack();
    var app = getApp();
    if (!app || typeof app.goHostHome !== "function") {
      wx.showToast({ title: "返回首页失败", icon: "none" });
      return;
    }
    app.goHostHome({
      onFail: function () {
        wx.showToast({ title: "返回首页失败", icon: "none" });
      },
    });
  },

  goWorkspaceBack: function () {
    helpers.vibrate("light");
    var workspaceBack = runtime.consumeWorkspaceBack(route.chat());
    if (workspaceBack && !flags.isRouteEnabled(workspaceBack.url)) {
      workspaceBack = null;
    }
    if (workspaceBack && workspaceBack.url) {
      wx.reLaunch({ url: workspaceBack.url });
      return;
    }
    this.goHome();
  },

  onNavBackTap: function () {
    helpers.vibrate("light");
    this.goHome();
  },

  _currentConversationIdForManage: function () {
    if (this.data.isStreaming) {
      wx.showToast({ title: "回答中暂不能操作", icon: "none" });
      return "";
    }
    var convId = String(this._convId || "").trim();
    if (!convId) {
      wx.showToast({ title: "当前对话尚未保存", icon: "none" });
      return "";
    }
    return convId;
  },

  onChatMoreActions: function () {
    var self = this;
    helpers.vibrate("light");
    if (!this._currentConversationIdForManage()) return;
    wx.showActionSheet({
      itemList: ["归档对话", "删除对话"],
      success: function (res) {
        if (res.tapIndex === 0) {
          self.archiveCurrentConversation();
        } else if (res.tapIndex === 1) {
          self.deleteCurrentConversation();
        }
      },
    });
  },

  archiveCurrentConversation: function () {
    var convId = this._currentConversationIdForManage();
    if (!convId) return;
    var self = this;
    wx.showModal({
      title: "归档对话",
      content: "归档后可在「历史-已归档」中查看和恢复。",
      confirmText: "归档",
      success: function (res) {
        if (!res.confirm) return;
        wx.showLoading({ title: "归档中..." });
        api
          .batchConversations("archive", [convId])
          .then(function () {
            wx.hideLoading();
            clearConversationHistoryCaches();
            wx.showToast({ title: "已归档", icon: "success" });
            self.goHome();
          })
          .catch(function () {
            wx.hideLoading();
            wx.showToast({ title: "归档失败", icon: "none" });
          });
      },
    });
  },

  deleteCurrentConversation: function () {
    var convId = this._currentConversationIdForManage();
    if (!convId) return;
    var self = this;
    wx.showModal({
      title: "删除对话",
      content: "确定要删除这条对话记录吗？删除后不可恢复。",
      confirmColor: "#ef4444",
      success: function (res) {
        if (!res.confirm) return;
        wx.showLoading({ title: "删除中..." });
        api
          .deleteConversation(convId)
          .then(function () {
            wx.hideLoading();
            rememberDeletedConversationIds([convId]);
            clearConversationHistoryCaches();
            wx.showToast({ title: "已删除", icon: "success" });
            self.goHome();
          })
          .catch(function () {
            wx.hideLoading();
            wx.showToast({ title: "删除失败", icon: "none" });
          });
      },
    });
  },

  goProfile: function () {
    if (!flags.isFeatureEnabled("profile")) {
      wx.showToast({ title: "我的暂未开放", icon: "none" });
      return;
    }
    runtime.clearWorkspaceBack();
    wx.navigateTo({ url: route.profile() });
  },

  /* 10d 三种历史归属①：会话历史 = 顶栏时钟图标二级页（复用 pages/history） */
  goHistoryPage: function () {
    if (!flags.isFeatureEnabled("history")) {
      wx.showToast({ title: "历史暂未开放", icon: "none" });
      return;
    }
    helpers.vibrate("light");
    wx.navigateTo({ url: route.history() });
  },

  /* 10d 快捷入口①：出几道题 —— 只预填出题意图，由用户确认后发送，不代发 */
  onQuickComposeQuestions: function () {
    if (this.data.canStopStream) return;
    helpers.vibrate("light");
    var query = "根据我的薄弱点出几道题让我练练";
    this._inputText = query;
    this.setData({ inputText: query });
  },

  /* 10d 快捷入口②：看动画讲解 —— 前端静态入口深链学习页有卡站，不造后端 */
  onQuickAnimLesson: function () {
    helpers.vibrate("light");
    wx.navigateTo({ url: route.lubanStations() });
  },

  /* 教学卡入口：pack 标题从 lessons API 兜底解析，失败保留 scene_title/pack_id */
  _resolveTeachEntryTitle: function (packId) {
    var self = this;
    if (typeof api.getLubanLessonDetail !== "function") return;
    api
      .getLubanLessonDetail(packId)
      .then(function (resp) {
        var body = unwrap(resp) || {};
        var title = String(body.title || "").trim();
        if (!title || !self._teachEntryIntent) return;
        self._teachEntryIntent = Object.assign({}, self._teachEntryIntent, {
          concept_label: title,
        });
        self.setData({
          contextBanner: buildContextBannerLabel(null, self._teachEntryIntent),
        });
      })
      .catch(function (err) {
        log.warn(
          "Chat",
          "teach entry title resolve degraded: " + ((err && err.message) || err),
        );
      });
  },

  /* 供测试触达文件内派生函数；运行时行为与直接调用等价 */
  _buildContextBannerLabel: function (followupQuestionContext, promptIntent) {
    return buildContextBannerLabel(followupQuestionContext, promptIntent);
  },

  _syncWorkspaceBack: function () {
    var workspaceBack = runtime.getWorkspaceBack(route.chat());
    if (workspaceBack && !flags.isRouteEnabled(workspaceBack.url)) {
      runtime.clearWorkspaceBack();
      workspaceBack = null;
    }
    this.setData({
      workspaceBackVisible: !!(workspaceBack && workspaceBack.url),
      workspaceBackLabel: workspaceBack ? workspaceBack.label : "返回",
    });
  },

  _shouldShowWorkspaceShell: function () {
    return flags.shouldShowWorkspaceShell();
  },

  _setWorkspaceShellHidden: function (hidden) {
    this._syncWorkspaceChrome({ hidden: !!hidden });
    // 五 tab 壳:问鲁班中央章 index=2
    helpers.syncTabBar(this, 2, {
      hidden: !!hidden,
    });
  },

  _syncMeasuredChatBottomSpacer: function (bottomBarBottom) {
    var self = this;
    if (!self.data.hasMessages || typeof self.createSelectorQuery !== "function") {
      return;
    }
    var viewportWidth = self.data.viewportWidth || 375;
    var unit = function (rpx) {
      return Math.round((viewportWidth * rpx) / 750);
    };
    var runMeasure = function () {
      var query = self.createSelectorQuery();
      if (!query || typeof query.select !== "function") return;
      query.select(".bottom-bar").boundingClientRect(function (rect) {
        if (!rect || !rect.height) return;
        var previousSpacer = self.data.chatBottomSpacer || 0;
        var measuredSpacer = Math.round(rect.height) + bottomBarBottom + unit(12);
        if (Math.abs((self.data.chatBottomSpacer || 0) - measuredSpacer) <= 1) {
          return;
        }
        var nextState = {
          chatBottomSpacer: measuredSpacer,
        };
        var delta = measuredSpacer - previousSpacer;
        if (Math.abs(delta) > 1) {
          var currentScrollTop = self._lastScrollY || self.data.chatScrollTop || 0;
          var compensatedScrollTop = Math.max(0, currentScrollTop + delta);
          nextState.chatScrollTop = compensatedScrollTop;
          self._lastScrollY = compensatedScrollTop;
        }
        self.setData(nextState);
      });
      if (typeof query.exec === "function") {
        query.exec();
      }
    };
    if (typeof wx !== "undefined" && wx && typeof wx.nextTick === "function") {
      wx.nextTick(runMeasure);
      return;
    }
    runMeasure();
  },

  onKeyboardFocus: function (e) {
    var detail = (e && e.detail) || {};
    this._syncWorkspaceChrome({ keyboardHeight: detail.height || 0 });
  },

  onKeyboardBlur: function () {
    this._syncWorkspaceChrome({ keyboardHeight: 0 });
  },

  _syncWorkspaceChrome: function (options) {
    var next = options && typeof options === "object" ? options : {};
    var previousHasMessages = !!this.data.hasMessages;
    var previousSpacer = this.data.chatBottomSpacer || 0;
    var hidden =
      next.hidden !== undefined ? !!next.hidden : !!this.data.workspaceShellHidden;
    var hasMessages =
      next.hasMessages !== undefined ? !!next.hasMessages : !!this.data.hasMessages;
    var keyboardHeight =
      next.keyboardHeight !== undefined
        ? Math.max(0, Number(next.keyboardHeight) || 0)
        : Math.max(0, Number(this.data.keyboardHeight) || 0);
    var viewportWidth = this.data.viewportWidth || 375;
    var safeBottom = this.data.safeBottom || 0;
    var shellHeight =
      this.data.workspaceShellHeight ||
      Math.round((viewportWidth * 140) / 750) + safeBottom;
    var shellVisible = flags.shouldShowWorkspaceShell() && !hidden;
    var unit = function (rpx) {
      return Math.round((viewportWidth * rpx) / 750);
    };
    var bottomBarBottom = keyboardHeight > 0 ? keyboardHeight : shellVisible ? shellHeight : 0;
    var bottomBarPaddingBottom = keyboardHeight > 0 ? unit(12) : shellVisible ? 0 : safeBottom + unit(12);
    var heroBottomSpacer = shellVisible ? shellHeight + unit(32) : unit(120);
    var chatBottomSpacer =
      unit(236) + bottomBarBottom + bottomBarPaddingBottom + unit(48);

    var nextState = {
      workspaceShellHidden: hidden,
      keyboardHeight: keyboardHeight,
      inputCursorSpacing: keyboardHeight > 0 ? unit(24) : Math.max(unit(24), safeBottom + unit(24)),
      heroBottomSpacer: heroBottomSpacer,
      chatBottomSpacer: chatBottomSpacer,
      bottomBarCompact: shellVisible,
      bottomBarStyle: hasMessages
        ? "bottom:" +
          bottomBarBottom +
          "px;padding-bottom:" +
          bottomBarPaddingBottom +
          "px;"
        : "",
    };
    var delta = chatBottomSpacer - previousSpacer;
    if (previousHasMessages && hasMessages && Math.abs(delta) > 1) {
      var currentScrollTop = this._lastScrollY || this.data.chatScrollTop || 0;
      var compensatedScrollTop = Math.max(0, currentScrollTop + delta);
      nextState.chatScrollTop = compensatedScrollTop;
      this._lastScrollY = compensatedScrollTop;
    }
    this.setData(nextState);
    if (hasMessages) {
      this._syncMeasuredChatBottomSpacer(bottomBarBottom);
    }
  },

  goRecharge: function () {
    wx.navigateTo({ url: route.billing() });
  },

  noop: function () {},

  closePaywall: function () {
    this.setData({ paywallVisible: false });
  },

  goPaywallBilling: function () {
    this.setData({ paywallVisible: false });
    wx.navigateTo({ url: route.billing() });
  },

  goQuickLogin: function () {
    runtime.redirectToLogin(route.chat({ preview: "1" }));
  },

  _showLoginGate: function (query, extraOpts) {
    var opts = extraOpts && typeof extraOpts === "object" ? extraOpts : {};
    var text = String(query || "").trim();
    if (text) {
      runtime.setPendingChatIntent(
        text,
        this.data.answerMode,
        opts.promptIntent || null,
        opts.followupQuestionContext || null,
      );
    }
    wx.showModal({
      title: "快速登录后继续",
      content: "当前问题已为你保留。登录后可继续答疑、批改和学习记录写回。",
      confirmText: "快速登录",
      cancelText: "继续浏览",
      success: function (res) {
        if (!res.confirm) return;
        runtime.redirectToLogin(route.chat({ preview: "1" }));
      },
    });
  },

  _showPaywall: function (payload) {
    var data = payload && typeof payload === "object" ? payload : {};
    this.setData({
      paywallVisible: true,
      paywallTitle: data.title || "需要开通后继续",
      paywallText: data.text || "这一步会消耗 AI 学习权益。开通后可以继续当前学习动作。",
    });
  },

  _isBillingBlockedMessage: function (message) {
    var legacyQuotaText = "额" + "度不足";
    return new RegExp(
      legacyQuotaText +
        "|权益不足|充值|开通|续费|billing_quota_exceeded|free_trial_|wallet balance",
      "i",
    ).test(String(message || ""));
  },

  onHeroMoreActions: function () {
    var self = this;
    var actions = [
      {
        label: "返回佑森首页",
        run: function () {
          self.goYousenHome();
        },
      },
      {
        label: this.data.isDark ? "切换浅色模式" : "切换深色模式",
        run: function () {
          self.onToggleTheme();
        },
      },
      {
        label: "权益中心",
        run: function () {
          self.goRecharge();
        },
      },
    ];
    if (this.data.profileEnabled) {
      actions.push({
        label: "个人中心",
        run: function () {
          self.goProfile();
        },
      });
    }
    helpers.vibrate("light");
    wx.showActionSheet({
      itemList: actions.map(function (action) {
        return action.label;
      }),
      success: function (res) {
        var action = actions[res.tapIndex];
        if (action && typeof action.run === "function") {
          action.run();
        }
      },
    });
  },

  onSwitchAccount: function () {
    wx.showModal({
      title: "切换账号",
      content: "确定要退出当前账号并切换吗？",
      confirmColor: "#ef4444",
      success: function (res) {
        if (res.confirm) {
          runtime.logout();
        }
      },
    });
  },

  onToggleTheme: function () {
    helpers.vibrate("light");
    var dark = !this.data.isDark;
    var themeVal = dark ? "dark" : "light";
    helpers.setTheme(themeVal); // 统一写入 globalData + Storage
    this.setData({ isDark: dark });
    this._setWorkspaceShellHidden(!this._shouldShowWorkspaceShell());
    wx.showToast({
      title: dark ? "深色模式" : "浅色模式",
      icon: "none",
      duration: 1000,
    });
  },

  _copyTextForMessage: function (msg) {
    if (!msg) return "";
    if (msg.role === "user") return String(msg.content || "").trim();

    var mcqText = this._copyTextFromMcqCards(msg.mcqCards || []);
    if (mcqText) return mcqText;

    var blockText = this._copyTextFromBlocks(msg.blocks || []);
    if (blockText) return blockText;

    return String(msg.renderableContent || msg.content || "").trim();
  },

  _copyTextFromMcqCards: function (cards) {
    if (!Array.isArray(cards) || !cards.length) return "";
    var parts = [];
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i] || {};
      var cardParts = [];
      var index = card.index || i + 1;
      var stem = String(card.stem || "").trim();
      if (stem) cardParts.push("第" + index + "题 " + stem);
      var options = Array.isArray(card.options) ? card.options : [];
      for (var j = 0; j < options.length; j++) {
        var option = options[j] || {};
        var key = String(option.key || "").trim();
        var text = String(option.text || "").trim();
        if (key || text) cardParts.push((key ? key + ". " : "") + text);
      }
      var cardText = this._joinCopyParts(cardParts);
      if (cardText) parts.push(cardText);
    }
    return this._joinCopyParts(parts);
  },

  _copyTextFromBlocks: function (blocks) {
    if (!Array.isArray(blocks) || !blocks.length) return "";
    var parts = [];
    for (var i = 0; i < blocks.length; i++) {
      var text = this._copyTextFromBlock(blocks[i]);
      if (text) parts.push(text);
    }
    return this._joinCopyParts(parts);
  },

  _copyTextFromBlock: function (block) {
    if (!block || typeof block !== "object") return "";
    var type = String(block.type || "").trim();
    if (type === "table") {
      var lines = [];
      var self = this;
      if (block.caption) lines.push(String(block.caption).trim());
      var headers = Array.isArray(block.headers) ? block.headers : [];
      if (headers.length) {
        lines.push(
          headers
            .map(function (cell) {
              return self._copyCellText(cell);
            })
            .join(" | "),
        );
      }
      var rows = Array.isArray(block.rows) ? block.rows : [];
      for (var r = 0; r < rows.length; r++) {
        var row = Array.isArray(rows[r]) ? rows[r] : [];
        if (row.length) {
          lines.push(
            row
              .map(function (cell) {
                return self._copyCellText(cell);
              })
              .join(" | "),
          );
        }
      }
      return this._joinCopyParts(lines, "\n");
    }
    if (type === "steps") {
      var stepParts = [];
      if (block.title) stepParts.push(String(block.title).trim());
      var steps = Array.isArray(block.steps) ? block.steps : [];
      for (var s = 0; s < steps.length; s++) {
        var step = steps[s] || {};
        var line = [
          step.index || s + 1,
          String(step.title || step.text || "").trim(),
          String(step.detail || "").trim(),
        ]
          .filter(function (item) {
            return String(item || "").trim();
          })
          .join(". ");
        if (line) stepParts.push(line);
      }
      return this._joinCopyParts(stepParts, "\n");
    }
    if (type === "recap") {
      var recapParts = [];
      if (block.title) recapParts.push(String(block.title).trim());
      if (block.summary) recapParts.push(String(block.summary).trim());
      var bullets = Array.isArray(block.bullets) ? block.bullets : [];
      for (var b = 0; b < bullets.length; b++) {
        var bullet = String(bullets[b] || "").trim();
        if (bullet) recapParts.push("- " + bullet);
      }
      return this._joinCopyParts(recapParts, "\n");
    }
    if (type === "chart") {
      var chartParts = [];
      if (block.title) chartParts.push(String(block.title).trim());
      if (block.summary) chartParts.push(String(block.summary).trim());
      var series = Array.isArray(block.series) ? block.series : [];
      for (var c = 0; c < series.length; c++) {
        var item = series[c] || {};
        var name = String(item.name || "").trim();
        var value = String(item.summary || item.value || "").trim();
        if (name || value) chartParts.push((name ? name + ": " : "") + value);
      }
      var tableText = this._copyTextFromChartTable(block.fallbackTable);
      if (tableText) chartParts.push(tableText);
      if (block.caption) chartParts.push(String(block.caption).trim());
      return this._joinCopyParts(chartParts, "\n");
    }
    if (type === "formula_block" || type === "formula_inline") {
      return String(block.copyText || block.displayText || block.latex || "").trim();
    }
    if (type === "ul" || type === "ol") {
      var itemParts = [];
      var items = Array.isArray(block.items) ? block.items : [];
      for (var i = 0; i < items.length; i++) {
        var item = items[i] || {};
        var prefix = type === "ol" ? String(item.index || i + 1) + ". " : "- ";
        var itemText = this._copyLooseText(
          item.nodes || item.content || item.children || item.raw || item.text || "",
        );
        if (itemText) itemParts.push(prefix + itemText);
      }
      return this._joinCopyParts(itemParts, "\n");
    }
    return this._copyLooseText(
      block.text ||
        block.raw ||
        block.content ||
        block.nodes ||
        block.children ||
        block.lineNodes ||
        block.summary ||
        block.title ||
        "",
    ).trim();
  },

  _copyTextFromChartTable: function (table) {
    if (!table || typeof table !== "object") return "";
    return this._copyTextFromBlock({
      type: "table",
      caption: table.caption || "",
      headers: table.headers || [],
      rows: table.rows || [],
    });
  },

  _copyCellText: function (cell) {
    return this._copyLooseText(cell).trim();
  },

  _copyInlineNodesText: function (nodes) {
    if (!Array.isArray(nodes) || !nodes.length) return "";
    var parts = [];
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i] || {};
      if (typeof node === "string") {
        parts.push(node);
        continue;
      }
      if (node.text) parts.push(String(node.text));
      if (node.value) parts.push(String(node.value));
      var childText = this._copyInlineNodesText(
        node.content || node.nodes || node.children || [],
      );
      if (childText) parts.push(childText);
    }
    return parts.join("").trim();
  },

  _copyLooseText: function (value) {
    if (value === null || typeof value === "undefined") return "";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    if (Array.isArray(value)) {
      var arrayParts = [];
      for (var i = 0; i < value.length; i++) {
        var itemText = this._copyLooseText(value[i]);
        if (itemText) arrayParts.push(itemText);
      }
      return arrayParts.join("");
    }
    if (typeof value === "object") {
      if (value.text || value.value || value.raw) {
        return String(value.text || value.value || value.raw);
      }
      var nested = this._copyLooseText(
        value.content || value.nodes || value.children || value.lineNodes || "",
      );
      if (nested) return nested;
      return String(
        value.copyText || value.displayText || value.latex || value.summary || value.title || value.detail || "",
      );
    }
    return "";
  },

  _joinCopyParts: function (parts, separator) {
    var self = this;
    return (parts || [])
      .map(function (item) {
        return self._copyLooseText(item).trim();
      })
      .filter(function (item) {
        return !!item;
      })
      .join(separator || "\n\n")
      .trim();
  },

  onCopy: function (e) {
    helpers.vibrate("light");
    var msg = this._getMessageById(e.currentTarget.dataset.msgid);
    var text = this._copyTextForMessage(msg);
    if (!text) {
      wx.showToast({ title: "暂无可复制内容", icon: "none" });
      return;
    }
    wx.setClipboardData({
      data: text,
      success: function () {
        wx.showToast({ title: "内容已复制", icon: "success", duration: 1200 });
      },
      fail: function (err) {
        if (typeof console !== "undefined" && console.warn) {
          console.warn("[chat] copy answer failed", err && err.errMsg ? err.errMsg : err);
        }
        wx.showToast({ title: "复制失败，请重试", icon: "none", duration: 1800 });
      },
    });
  },

  _trackNotebookCardEvent: function (eventName, opts) {
    var options = opts || {};
    if (!surfaceTelemetry || !surfaceTelemetry.trackProductBehavior) return;
    surfaceTelemetry.trackProductBehavior(eventName, {
      module: "chat",
      section: "note_assets",
      action: options.action || "save_note",
      objectType: "notebook_card",
      objectId: options.objectId || "",
      entrySource: "chat_answer",
      result: options.result || "",
      errorCode: options.errorCode || "",
      sessionId: String(this.data.currentSessionId || this.data.conversationId || ""),
      turnId: options.turnId || "",
    });
  },

  onSaveNotebookCard: function (e) {
    helpers.vibrate("light");
    var msg = this._getMessageById(e.currentTarget.dataset.msgid);
    if (!msg || !api.saveNotebookCard) {
      wx.showToast({ title: "这条回答暂不能存卡", icon: "none", duration: 1600 });
      return;
    }
    var msgId = String(msg.id || "").trim();
    var turnId = String(msg.turnId || msg.turn_id || "").trim();
    var text = this._copyTextForMessage(msg).slice(0, 500);
    var title = String(msg.title || text.split("\n")[0] || "答疑学习卡").slice(0, 80);
    var self = this;
    this._trackNotebookCardEvent("note_card_suggested", {
      action: "suggest",
      objectId: msgId,
      turnId: turnId,
    });
    api.saveNotebookCard({
      card_type: "review_note",
      source_type: "chat",
      source_ref: { message_id: msgId, turn_id: turnId },
      title: title,
      user_query: "保存答疑学习卡",
      output: "",
      ai_enhanced_content: { summary: text.slice(0, 180) },
    }).then(function (saved) {
      var noteId = String(
        (saved && saved.note_id) ||
          (saved && saved.card && saved.card.note_id) ||
          msgId ||
          "",
      );
      self._trackNotebookCardEvent("note_card_saved", {
        action: "save_note",
        objectId: noteId,
        turnId: turnId,
        result: "success",
      });
      wx.showToast({ title: "已保存学习卡", icon: "success", duration: 1400 });
    }).catch(function () {
      self._trackNotebookCardEvent("note_card_rejected", {
        action: "reject",
        objectId: msgId,
        turnId: turnId,
        result: "failed",
        errorCode: "save_failed",
      });
      wx.showToast({ title: "保存失败，请稍后重试", icon: "none", duration: 1800 });
    });
  },

  onToggleWorkflowTrace: function (e) {
    helpers.vibrate("light");
    var idx = this._find(e.currentTarget.dataset.msgid);
    if (idx === -1) return;
    var current = !!this.data.messages[idx].workflowExpanded;
    this.setData({
      ["messages[" + idx + "].workflowExpanded"]: !current,
    });
  },

  onToggleOriginalContent: function (e) {
    helpers.vibrate("light");
    var idx = this._find(e.currentTarget.dataset.msgid);
    if (idx === -1) return;
    var msg = this.data.messages[idx] || {};
    if (!msg.originalContent) return;
    this.setData({
      ["messages[" + idx + "].originalExpanded"]: !msg.originalExpanded,
    });
  },

  onEdit: function (e) {
    helpers.vibrate("light");
    var msg = this._getMessageById(e.currentTarget.dataset.msgid);
    if (msg) {
      this._inputText = msg.content;
      this.setData({ inputText: msg.content });
      if (this.data.isStreaming) {
        wx.showToast({ title: "已停止本轮，可修改后重发", icon: "none", duration: 1800 });
        this._stop({ cancelTurn: true });
      }
    }
  },

  onRetry: function (e) {
    if (this.data.isStreaming) return;
    helpers.vibrate("medium");
    var msgid = e.currentTarget.dataset.msgid;
    var msgs = this.data.messages;
    var aiIdx = this._find(msgid);
    if (aiIdx <= 0) return;
    // 找到这条 AI 消息前面的用户消息
    var userMsg = null;
    for (var j = aiIdx - 1; j >= 0; j--) {
      if (msgs[j].role === "user") {
        userMsg = msgs[j];
        break;
      }
    }
    if (!userMsg) return;
    // 移除旧的 AI 回复，重新发送
    var newMsgs = msgs.slice(0, aiIdx);
    this._syncMessageIndexMap(newMsgs);
    this.setData({ messages: newMsgs });
    var retryOptions = {
      reuseUserMessage: true,
      persistUserMessage: false,
    };
    if (userMsg.followupQuestionContext && typeof userMsg.followupQuestionContext === "object") {
      retryOptions.followupQuestionContext = userMsg.followupQuestionContext;
    }
    if (userMsg.structuredSubmitContext && typeof userMsg.structuredSubmitContext === "object") {
      retryOptions.structuredSubmitContext = userMsg.structuredSubmitContext;
    }
    if (userMsg.promptIntent && typeof userMsg.promptIntent === "object") {
      retryOptions.promptIntent = userMsg.promptIntent;
    }
    this._send(userMsg.content, retryOptions);
  },

  onThumbUp: function (e) {
    helpers.vibrate("light");
    var msgid = e.currentTarget.dataset.msgid;
    var idx = this._find(msgid);
    if (idx === -1) return;
    var current = this.data.messages[idx].feedback;
    var isUndo = current === "up";
    // 如果之前是 down 弹窗，先关闭
    var updates = {};
    updates["messages[" + idx + "].feedback"] = isUndo ? "" : "up";
    if (this.data.feedbackMsgId === msgid) {
      updates.feedbackMsgId = "";
      updates.feedbackTags = [];
      updates.feedbackComment = "";
    }
    this.setData(updates);
    if (!isUndo) {
      this._sendFeedback(msgid, 1, [], "");
    }
  },

  onThumbDown: function (e) {
    helpers.vibrate("light");
    var msgid = e.currentTarget.dataset.msgid;
    var idx = this._find(msgid);
    if (idx === -1) return;
    var current = this.data.messages[idx].feedback;
    var isUndo = current === "down";
    this.setData({
      ["messages[" + idx + "].feedback"]: isUndo ? "" : "down",
      feedbackMsgId: isUndo ? "" : msgid,
      feedbackTags: [],
      feedbackComment: "",
      scrollToId: isUndo ? this.data.scrollToId : "msg-bottom",
      chatScrollWithAnimation: !isUndo,
    });
  },

  onFeedbackTag: function (e) {
    if (this.data.feedbackSubmitting) return;
    var tag = String((e.currentTarget.dataset || {}).tag || "").trim();
    if (!tag) return;
    var tags = this.data.feedbackTags.slice();
    var i = tags.indexOf(tag);
    if (i >= 0) {
      tags.splice(i, 1);
    } else {
      tags.push(tag);
    }
    this.setData({ feedbackTags: tags });
  },

  onFeedbackInput: function (e) {
    if (this.data.feedbackSubmitting) return;
    this.setData({ feedbackComment: e.detail.value });
  },

  onFeedbackSubmit: function () {
    if (this.data.feedbackSubmitting) return;
    var msgid = this.data.feedbackMsgId;
    if (!msgid) return;
    var self = this;
    this.setData({ feedbackSubmitting: true });
    var request = this._sendFeedback(
      msgid,
      -1,
      this.data.feedbackTags,
      this.data.feedbackComment,
    );
    var finishSuccess = function () {
      wx.showToast({ title: "感谢反馈", icon: "success", duration: 1500 });
      self.setData({
        feedbackMsgId: "",
        feedbackTags: [],
        feedbackComment: "",
        feedbackSubmitting: false,
      });
    };
    var finishFailure = function () {
      wx.showToast({ title: "提交失败，请稍后重试", icon: "none", duration: 1800 });
      self.setData({ feedbackSubmitting: false });
    };
    if (request && typeof request.then === "function") {
      request.then(finishSuccess).catch(finishFailure);
    } else {
      finishSuccess();
    }
  },

  onFeedbackClose: function () {
    if (this.data.feedbackSubmitting) return;
    this.setData({ feedbackMsgId: "", feedbackTags: [], feedbackComment: "" });
  },

  onToggleCitationQuote: function (e) {
    var dataset = (e && e.currentTarget && e.currentTarget.dataset) || {};
    var msgid = String(dataset.msgid || "").trim();
    var citeIndex = Number(dataset.citeindex);
    var idx = this._find(msgid);
    if (idx === -1 || !Number.isFinite(citeIndex) || citeIndex < 0) return;
    var msg = this.data.messages[idx] || {};
    var citations = Array.isArray(msg.citations) ? msg.citations : [];
    var current = citations[citeIndex];
    if (!current || !current.quote) return;
    var expanded = !current.quoteExpanded;
    var updates = {};
    updates["messages[" + idx + "].citations[" + citeIndex + "].quoteExpanded"] = expanded;
    updates["messages[" + idx + "].citations[" + citeIndex + "].quoteActionText"] = expanded
      ? "收起摘录"
      : "查看摘录";
    this.setData(updates);
  },

  // [W5-1] Network restored — refresh dashboard and hint user about failed messages
  onNetworkRestore: function () {
    this._loadDashboard();
    // Check if any messages failed during offline period
    var msgs = this.data.messages;
    var hasError = false;
    for (var i = 0; i < msgs.length; i++) {
      if (
        msgs[i].role === "ai" &&
        msgs[i].content === "" &&
        !msgs[i].streaming
      ) {
        hasError = true;
        break;
      }
    }
    if (hasError) {
      wx.showToast({
        title: "网络已恢复，可点击重试",
        icon: "none",
        duration: 2000,
      });
    }
  },

  _sendFeedback: function (msgid, rating, tags, comment) {
    var msg = this._getMessageById(msgid);
    return api.submitFeedback({
      message_id: msgid,
      conversation_id: this._convId || "",
      turn_id: (msg && msg.engineTurnId) || "",
      rating: rating,
      reason_tags: tags || [],
      comment: comment || "",
      answer_mode: this.data.answerMode || "AUTO",
    });
  },

  _getMessageById: function (id) {
    var idx = this._find(id);
    if (idx === -1) return null;
    return this.data.messages[idx] || null;
  },
});
