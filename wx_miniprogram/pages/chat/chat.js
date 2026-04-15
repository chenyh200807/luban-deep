// pages/chat/chat.js — 1:1 复刻 Web 手机端
var auth = require("../../utils/auth");
var api = require("../../utils/api");
var unwrap = api.unwrapResponse;
var md = require("../../utils/markdown");
var mcqDetect = require("../../utils/mcq-detect");
var wsStream = require("../../utils/ws-stream");
var helpers = require("../../utils/helpers");
var log = require("../../utils/logger");
var workflowStatus = require("../../utils/workflow-status");
var citationFormat = require("../../utils/citation-format");

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
var AUTO_WEB_SEARCH_PATTERNS = [
  /(最新|最近|当前|现行|今年|本月|本周|今天|近期)/,
  /(新规|新版|新政策|政策调整|政策变化|新通知|新公告|新文件)/,
  /(政策|通知|公告|通告|发文|实施时间|什么时候实施|何时实施)/,
  /(住建部|住房和城乡建设部|建标|国标|地标|规范更新|标准更新)/,
  /(202[4-9]|20[3-9]\d).{0,12}(政策|规范|标准|通知|公告|文件|变化|更新)?/,
];

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    safeBottom: 0,
    viewportHeight: 0,
    contentHeight: 0,
    hasMessages: false,
    messages: [],
    inputText: "",
    isStreaming: false,
    scrollToId: "",
    chatScrollWithAnimation: false,
    answerMode: "AUTO",
    modeHintText: "TutorBot 陪学 · 智能调度",
    enableReason: false,
    enableWebSearch: false,
    feedbackMsgId: "",
    feedbackTags: [],
    feedbackComment: "",
    isDark: true,
    // 性能分级：控制 WXML 中动效开关
    enableOrbs: _animCfg.enableBreathingOrbs,
    enableMarquee: _animCfg.enableMarquee,
    enableMsgAnim: _animCfg.enableMsgAnimation,
    enableFocusPulse: _animCfg.enableFocusPulse,

    // 积分弹窗
    billingShow: false,
    billingBalance: 0,
    billingLoading: false,
    billingEntries: [],

    // Hero
    userName: "用户",
    timeGreeting: helpers.getTimeGreeting(),
    userPoints: 0,
    avatarChar: "U",
    reviewCount: 0,
    focusText: "",
    focusQuery: "",

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
        desc: "一建考点梳理",
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
  _observer: null, // IntersectionObserver 用于懒解析 Markdown
  _visibleSet: {}, // 当前可见消息 id 集合
  _autoScrollEnabled: true,

  // ── 生命周期 ──────────────────────────────────

  onLoad: function () {
    var info = helpers.getWindowInfo();
    var savedToolPrefs = wx.getStorageSync(CHAT_TOOL_PREFS_KEY) || {};
    var statusBarHeight = info.statusBarHeight || 44;
    var navHeight = statusBarHeight + 44;
    var viewportHeight = info.windowHeight || info.screenHeight || 812;
    var safeBottom = info.safeArea
      ? info.screenHeight - info.safeArea.bottom
      : 0;
    var contentHeight = Math.max(viewportHeight - navHeight, 320);

    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: navHeight,
      safeBottom: safeBottom,
      viewportHeight: viewportHeight,
      contentHeight: contentHeight,
      isDark: helpers.isDark(),
      enableReason: !!savedToolPrefs.enableReason,
      enableWebSearch: false,
    });
    if (savedToolPrefs.enableWebSearch) {
      this._saveToolPrefs(!!savedToolPrefs.enableReason, false);
    }

    // [FIX-SESSION-1] 仅在 5 分钟内恢复 session（处理页面刷新），
    // 超时则开启新对话，防止所有问题堆积在同一个历史记录中
    var savedSessionId = wx.getStorageSync("current_session_id");
    var savedTs = wx.getStorageSync("current_session_ts") || 0;
    var SESSION_MAX_AGE_MS = 5 * 60 * 1000; // 5 分钟过期

    if (savedSessionId && Date.now() - savedTs < SESSION_MAX_AGE_MS) {
      this._sid = savedSessionId;
      this._convId = savedSessionId;
    } else {
      this._sid = "s_" + Date.now();
      this._convId = null;
      wx.removeStorageSync("current_session_id");
      wx.removeStorageSync("current_session_ts");
    }
  },

  onShow: function () {
    var self = this;
    var dark = helpers.isDark();
    this.setData({ isDark: dark });
    helpers.syncTabBar(this, 0, { hidden: this.data.hasMessages });
    var app = getApp();
    // 从其他页面点 logo 回来，清消息回到 Hero 主页
    if (app.globalData.goHomeFlag) {
      app.globalData.goHomeFlag = false;
      this.clearMessages();
    }
    // 从历史记录恢复对话
    if (app.globalData.pendingConversationId) {
      var convId = app.globalData.pendingConversationId;
      app.globalData.pendingConversationId = null;
      self._restoreConversation(convId);
    }
    app.checkAuth(function () {
      self.setData({ timeGreeting: helpers.getTimeGreeting() });
      // 用 getUserInfo 验证 token 是否真的有效
      api
        .getUserInfo()
        .then(function (raw) {
          var info = api.unwrapResponse(raw);
          var name = info.username || info.display_name || "用户";
          // 保存 userId 供统一聊天运行时使用
          var uid = info.id || info.user_id;
          if (uid) auth.setToken(auth.getToken(), uid);
          self.setData({
            userName: name,
            avatarChar: name.charAt(0).toUpperCase(),
            userPoints: info.points || 0,
          });
        })
        .catch(function (e) {
          log.warn("Chat", "getUserInfo failed: " + ((e && e.message) || e));
          // 401 已被 api.js 拦截跳转登录
        });
      // 获取首页仪表盘数据（复习/薄弱点）
      self._loadDashboard();
      // 新用户弹窗：建议做摸底测试
      self._checkDiagnostic();
      var pendingQuery = app.globalData.pendingChatQuery;
      var pendingMode = app.globalData.pendingChatMode || "AUTO";
      if (pendingQuery && !self.data.isStreaming) {
        app.globalData.pendingChatQuery = "";
        app.globalData.pendingChatMode = "AUTO";
        self.setData({ answerMode: pendingMode });
        self._send(pendingQuery);
      }
    });
    // [FIX] 从后台切回时重建 observer（onHide 中已 teardown）
    if (this.data.hasMessages) {
      this._setupObserver();
    }
  },

  onHide: function () {
    // [FIX] 切后台时不中断流式会话，只暂停 observer 降低内存开销。
    // 切回 onShow 时流式输出继续，避免用户切 app 后内容断掉。
    // 只有 onUnload（页面销毁）才调 _stop() 中断连接。
    this._teardownObserver();
  },
  onUnload: function () {
    this._stop();
    this._teardownObserver();
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
          (!msgs[i].blocks || !msgs[i].blocks.length)
        ) {
          update["messages[" + i + "].blocks"] = md.parseWithIds(
            this._getRenderableAiText(msgs[i].content),
          );
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

  _lazyParseBlocks: function (msgId) {
    var idx = this._find(msgId);
    if (idx === -1) return;
    var msg = this.data.messages[idx];
    // 正在流式的消息由 _flush 管理，不在此处理
    if (msg.streaming) return;
    // 已有 blocks 则跳过
    if (msg.blocks && msg.blocks.length > 0) return;
    // 无内容则跳过
    if (!msg.content || msg.role !== "ai") return;
    this.setData({
      ["messages[" + idx + "].blocks"]: md.parseWithIds(
        this._getRenderableAiText(msg.content),
      ),
    });
  },

  // ── 流式控制 ──────────────────────────────────

  _stop: function () {
    if (this._abort) {
      try {
        this._abort();
      } catch (_) {}
      this._abort = null;
    }
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    this._buf = "";
  },

  _onToken: function (t) {
    this._buf += t;
    if (!this._timer) {
      var self = this;
      this._timer = setInterval(function () {
        self._flush();
      }, FLUSH_THROTTLE_MS);
    }
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
    var renderableText = this._getRenderableAiText(newContent);
    this._buf = "";
    this._flushCount++;

    var update = {};
    update["messages[" + idx + "].content"] = newContent;
    update["messages[" + idx + "].renderableContent"] = renderableText;
    if (this._autoScrollEnabled) {
      update.scrollToId = "msg-bottom";
      update.chatScrollWithAnimation = false;
    }

    // 实时 Markdown：首次立即解析，之后每 N 次 flush 解析一次
    if (this._flushCount <= 1 || this._flushCount % MD_PARSE_INTERVAL === 0) {
      update["messages[" + idx + "].blocks"] = md.parseWithIds(renderableText);
    }

    this.setData(update);
  },

  _onDone: function () {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    this._abort = null;
    if (this._buf) this._flush();

    var idx = this._find(this._streamId);
    if (idx !== -1) {
      var currentMsg = this.data.messages[idx];
      var text = currentMsg.content;
      var detectedMcq = mcqDetect.detect(text);
      var existingCards = currentMsg.mcqCards;
      var renderText =
        detectedMcq && detectedMcq.displayText !== undefined
          ? detectedMcq.displayText
          : mcqDetect.stripReceipt(text);
      var u = {};
      u["messages[" + idx + "].streaming"] = false;
      u["messages[" + idx + "].renderableContent"] = renderText || "";
      u["messages[" + idx + "].blocks"] = md.parseWithIds(renderText || "");
      if (renderText || (currentMsg.blocks && currentMsg.blocks.length)) {
        u["messages[" + idx + "].thinkingStatus"] = "";
        u["messages[" + idx + "].thinkingBadge"] = "";
        u["messages[" + idx + "].thinkingSub"] = "";
        u["messages[" + idx + "].thinkingTone"] = "";
      }
      if ((!existingCards || !existingCards.length) && detectedMcq) {
        var fallbackState = this._buildFallbackMcqState(detectedMcq);
        if (fallbackState) {
          u["messages[" + idx + "].mcqCards"] = fallbackState.cards;
          u["messages[" + idx + "].mcqHint"] = fallbackState.hint;
          u["messages[" + idx + "].mcqReceipt"] = fallbackState.receipt;
          u["messages[" + idx + "].mcqInteractiveReady"] = fallbackState.interactiveReady;
        }
      } else if (detectedMcq && detectedMcq.receipt) {
        u["messages[" + idx + "].mcqReceipt"] = detectedMcq.receipt;
      }
      u.isStreaming = false;
      if (this._autoScrollEnabled) {
        u.scrollToId = "msg-bottom";
        u.chatScrollWithAnimation = false;
      } else {
        u.scrollToId = "";
        u.chatScrollWithAnimation = false;
      }
      this.setData(u);
      if (this._autoScrollEnabled) {
        var self = this;
        setTimeout(function () {
          self._releaseBottomAnchor();
        }, 80);
      }
    } else {
      this.setData({ isStreaming: false });
    }
    this._streamId = null;
  },

  _onError: function (m) {
    var idx = this._find(this._streamId);
    if (idx !== -1) {
      var msg = this.data.messages[idx];
      var state = this._buildWorkflowState(msg, {
        eventType: "progress",
        stage: "retry",
        data: m || "服务异常",
      }, false);
      this._setWorkflowState(idx, state, false);
    }
    this._onDone();
    wx.showToast({ title: m || "回复失败", icon: "none" });
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
    var preserveThinking = !!(msg.content || (msg.blocks && msg.blocks.length));
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

  _onFinal: function (d) {
    if (!d) return;
    var idx = this._find(this._streamId);
    if (idx !== -1) {
      var updates = {};
      if (d.citations) {
        updates["messages[" + idx + "].citations"] =
          citationFormat.formatCitations(d.citations);
      }
      if (d.engine) {
        updates["messages[" + idx + "].engine"] = d.engine;
      }
      if (d.engine_session_id) {
        updates["messages[" + idx + "].engineSessionId"] = d.engine_session_id;
      }
      if (d.engine_turn_id) {
        updates["messages[" + idx + "].engineTurnId"] = d.engine_turn_id;
      }
      if (d.billing && typeof d.billing === "object") {
        updates["messages[" + idx + "].billing"] = d.billing;
        if (typeof d.billing.balance_after === "number") {
          updates.billingBalance = d.billing.balance_after;
        }
      }
      if (Object.keys(updates).length) {
        this.setData(updates);
      }
    }
  },

  _onMcqInteractive: function (d) {
    if (!d || !d.questions || !d.questions.length) return;
    var idx = this._find(this._streamId);
    if (idx === -1) return;
    var state = this._buildInteractiveMcqState(d);
    if (!state) return;
    this.setData({
      ["messages[" + idx + "].mcqCards"]: state.cards,
      ["messages[" + idx + "].mcqHint"]: state.hint,
      ["messages[" + idx + "].mcqReceipt"]: state.receipt,
      ["messages[" + idx + "].mcqInteractiveReady"]: state.interactiveReady,
    });
  },

  _find: function (id) {
    if (id === null) return -1;
    var msgs = this.data.messages;
    for (var i = 0; i < msgs.length; i++) {
      if (msgs[i].id === id) return i;
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
    updates["messages[" + idx + "].workflowToggleText"] = summary.toggleText || "展开后台过程";
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

  _normalizeMcqOptions: function (rawOptions) {
    var options = [];
    if (Array.isArray(rawOptions)) {
      for (var i = 0; i < rawOptions.length; i++) {
        var opt = rawOptions[i];
        if (!opt || !opt.key) continue;
        options.push({
          key: String(opt.key).toUpperCase(),
          text: opt.text || "",
          selected: !!opt.selected,
        });
      }
      return options;
    }
    if (!rawOptions || typeof rawOptions !== "object") return options;
    var keys = Object.keys(rawOptions).sort();
    for (var j = 0; j < keys.length; j++) {
      var key = keys[j];
      options.push({
        key: String(key).toUpperCase(),
        text: rawOptions[key] || "",
        selected: false,
      });
    }
    return options;
  },

  _buildDetectedMcqCards: function (detected) {
    if (!detected) return [];
    if (Array.isArray(detected.questions) && detected.questions.length) {
      return this._buildEventMcqCards(detected.questions);
    }
    if (!detected.options || detected.options.length < 2) return [];
    return [
      {
        index: 1,
        stem: detected.stem || "请选择正确选项",
        hint: "",
        questionType: detected.questionType || "single_choice",
        options: this._normalizeMcqOptions(detected.options),
        followupContext: null,
        questionId: "",
        hasContext: false,
      },
    ];
  },

  _buildEventMcqCards: function (questions) {
    var cards = [];
    var items = Array.isArray(questions) ? questions : [];
    for (var i = 0; i < items.length; i++) {
      var q = items[i];
      if (!q) continue;
      var options = this._normalizeMcqOptions(q.options);
      if (options.length < 2) continue;
      cards.push({
        index: q.index || i + 1,
        stem: q.stem || "请选择正确选项",
        hint: q.hint || "",
        questionType: q.question_type || "single_choice",
        options: options,
        followupContext:
          q.followup_context && typeof q.followup_context === "object"
            ? q.followup_context
            : null,
        questionId: String(
          q.question_id ||
            (q.followup_context && q.followup_context.question_id) ||
            "",
        ).trim(),
        hasContext: !!(
          q.followup_context &&
          typeof q.followup_context === "object" &&
          q.followup_context.question_id
        ),
      });
    }
    return cards;
  },

  _buildInteractiveMcqState: function (interactive) {
    if (!interactive || !Array.isArray(interactive.questions) || !interactive.questions.length) {
      return null;
    }
    var rawQuestions = [];
    var hiddenContexts = Array.isArray(interactive.hidden_contexts)
      ? interactive.hidden_contexts
      : [];
    for (var i = 0; i < interactive.questions.length; i++) {
      var question = interactive.questions[i] || {};
      rawQuestions.push(
        Object.assign({}, question, {
          followup_context:
            hiddenContexts[i] && typeof hiddenContexts[i] === "object"
              ? hiddenContexts[i]
              : null,
        }),
      );
    }
    var cards = this._buildEventMcqCards(rawQuestions);
    if (!cards.length) return null;
    return {
      cards: cards,
      hint: interactive.submit_hint || "请选择后提交答案",
      receipt: interactive.receipt || "",
      interactiveReady: true,
    };
  },

  _buildFallbackMcqState: function (detected) {
    var cards = this._buildDetectedMcqCards(detected);
    if (!cards.length) return null;
    return {
      cards: cards,
      hint: "当前题卡缺少原始上下文，仅供查看；如需作答，请让 AI 重新出题。",
      receipt: detected && detected.receipt ? detected.receipt : "",
      interactiveReady: false,
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
    if (missingContext) return { error: "missing_context" };
    var rows = [];
    for (var k = 0; k < selections.length; k++) {
      rows.push("第" + selections[k].index + "题：" + selections[k].keys.join("、"));
    }
    var followupQuestionContext = null;
    if (selections.length === 1) {
      for (var m = 0; m < items.length; m++) {
        var singleCard = items[m];
        if (!singleCard || !singleCard.followupContext) continue;
        if (Number(singleCard.index) !== Number(selections[0].index)) continue;
        followupQuestionContext = Object.assign({}, singleCard.followupContext, {
          user_answer: selections[0].keys.join(""),
        });
        break;
      }
    } else {
      var compositeItems = [];
      var questionLines = [];
      for (var n = 0; n < items.length; n++) {
        var compositeCard = items[n];
        if (!compositeCard || !compositeCard.followupContext) continue;
        compositeItems.push(
          Object.assign({}, compositeCard.followupContext, {
            user_answer: this._selectedMcqKeys(compositeCard).join(""),
          }),
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
    return {
      text: text,
      structuredSubmitContext: {
        questions: structuredQuestions,
        answers: structuredAnswers,
      },
      followupQuestionContext: followupQuestionContext,
    };
  },

  _getRenderableAiText: function (content) {
    var detected = mcqDetect.detect(content);
    if (detected && detected.displayText !== undefined) {
      return detected.displayText || "";
    }
    return mcqDetect.stripReceipt(content || "");
  },

  // ── 仪表盘 ─────────────────────────────────────

  _loadDashboard: function () {
    var self = this;
    api
      .getHomeDashboard()
      .then(function (resp) {
        var d = unwrap(resp) || {};
        var review = d.review || {};
        var mastery = d.mastery || {};
        var today = d.today || {};
        var overdue = review.overdue || 0;
        var dueToday = review.due_today || 0;

        var update = {};
        update.reviewCount = overdue + dueToday;

        // 构建今日焦点：优先薄弱点速练，其次 hint
        var weakNodes = mastery.weak_nodes || [];
        if (weakNodes.length > 0) {
          var node = weakNodes[0];
          var name =
            (node.name || "").length > 8
              ? node.name.substring(0, 8)
              : node.name || "";
          update.focusText = "今日焦点：薄弱点速练：5 题 · " + name;
          update.focusQuery = "我想练习" + (node.name || "") + "相关的题目";
        } else if (overdue > 0) {
          update.focusText = "今日焦点：" + overdue + " 个逾期复习待处理";
          update.focusQuery = "帮我复习逾期的知识点";
        } else if (today.hint) {
          update.focusText = "今日焦点：" + today.hint;
          update.focusQuery = "继续我的学习计划";
        } else {
          // 降级：始终显示焦点条
          update.focusText = "今日焦点：保持节奏，继续推进学习计划";
          update.focusQuery = "继续我的学习计划";
        }

        self.setData(update);
      })
      .catch(function (err) {
        log.warn("Dashboard", "API failed: " + ((err && err.message) || err));
        // 降级：仍显示默认焦点条
        self.setData({
          focusText: "今日焦点：保持节奏，继续推进学习计划",
          focusQuery: "继续我的学习计划",
        });
      });
  },

  onFocusTap: function () {
    var query = this.data.focusQuery;
    if (query && !this.data.isStreaming) {
      this._send(query);
    }
  },

  // ── Hero 弹性拖拽 + 震动 ───────────────────────
  _onHeroDragStart: function (e) {
    this._dragStartY = e.touches[0].clientY;
    this._dragVibrated = false;
    this.setData({ _heroDragTransition: "none" });
  },
  _onHeroDragMove: function (e) {
    if (!this._dragStartY) return;
    var delta = e.touches[0].clientY - this._dragStartY;
    // 阻尼系数：拖得越远阻力越大
    var damped =
      delta > 0
        ? Math.min(HERO_MAX_DRAG_PX, delta * HERO_DRAG_DAMPING)
        : Math.max(-HERO_MAX_DRAG_PX, delta * HERO_DRAG_DAMPING);
    this.setData({ _heroDragY: damped });
    // 超过阈值时震动一次
    if (!this._dragVibrated && Math.abs(damped) > HERO_VIBRATE_THRESHOLD_PX) {
      this._dragVibrated = true;
      helpers.vibrate("light");
    }
  },
  _onHeroDragEnd: function () {
    this._dragStartY = null;
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
    var nextState = {
      answerMode: nextMode,
      modeHintText: this._getModeHintText(nextMode),
    };
    if (nextMode !== "DEEP" && this.data.enableReason) {
      nextState.enableReason = false;
      this._saveToolPrefs(false, this.data.enableWebSearch);
      wx.showToast({ title: "非深度模式已关闭推理", icon: "none", duration: 1800 });
    }
    this.setData(nextState);
  },

  onToggleReason: function () {
    helpers.vibrate("light");
    var nextReason = !this.data.enableReason;
    var nextMode = this.data.answerMode;
    if (nextReason && nextMode !== "DEEP") {
      nextMode = "DEEP";
      wx.showToast({ title: "已切换到深度模式", icon: "none", duration: 1800 });
    }
    this._saveToolPrefs(nextReason, this.data.enableWebSearch);
    this.setData({
      enableReason: nextReason,
      answerMode: nextMode,
      modeHintText: this._getModeHintText(nextMode),
    });
  },

  onToggleWebSearch: function () {
    helpers.vibrate("light");
    var nextWebSearch = !this.data.enableWebSearch;
    this._saveToolPrefs(this.data.enableReason, nextWebSearch);
    this.setData({ enableWebSearch: nextWebSearch });
  },

  _saveToolPrefs: function (enableReason, enableWebSearch) {
    wx.setStorageSync(CHAT_TOOL_PREFS_KEY, {
      enableReason: !!enableReason,
      enableWebSearch: !!enableWebSearch,
    });
  },

  _shouldAutoEnableWebSearch: function (query) {
    var text = String(query || "").trim();
    if (!text) return false;
    for (var i = 0; i < AUTO_WEB_SEARCH_PATTERNS.length; i++) {
      if (AUTO_WEB_SEARCH_PATTERNS[i].test(text)) return true;
    }
    return false;
  },

  _getSelectedTools: function (query) {
    var tools = [];
    if (this.data.enableReason) tools.push("reason");
    if (this.data.enableWebSearch || this._shouldAutoEnableWebSearch(query)) {
      tools.push("web_search");
    }
    return tools;
  },

  _getModeHintText: function (mode) {
    if (mode === "FAST") return "TutorBot 快答 · 踩分点优先";
    if (mode === "DEEP") return "TutorBot 精讲 · 讲透拿分逻辑";
    return "TutorBot 陪学 · 智能调度";
  },

  _buildTutorInteraction: function () {
    var mode = String(this.data.answerMode || "AUTO").toUpperCase();
    return {
      profile: "mini_tutor",
      hints: {
        product_surface: "wechat_miniprogram",
        entry_role: "tutorbot",
        subject_domain: "construction_exam",
        teaching_mode:
          mode === "FAST" ? "fast" : mode === "DEEP" ? "deep" : "smart",
        pedagogy_contract: "construction_exam_tutor_v1",
      },
    };
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
    var tab = typeof this.getTabBar === "function" && this.getTabBar();
    if (!tab) return;
    if (y < lastY - 5) {
      // 上滑（往回看历史）→ 显示 tab bar
      if (tab.data.hidden) {
        tab.setData({ hidden: false });
        this._scrollToggleTime = now;
      }
    } else if (y > lastY + 5) {
      // 下滑（看最新消息）→ 隐藏 tab bar
      if (!tab.data.hidden) {
        tab.setData({ hidden: true });
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
    if (!getApp().globalData.networkAvailable) {
      wx.showToast({ title: "当前无网络连接", icon: "none", duration: 2000 });
      return;
    }
    var text = (this._inputText || this.data.inputText || "").trim();
    if (!text || this.data.isStreaming) return;
    helpers.vibrate("medium");
    this._inputText = "";
    this.setData({ inputText: "" });
    this._send(text);
  },

  sendExample: function (e) {
    if (this.data.isStreaming) return;
    helpers.vibrate("light");
    this._send(e.currentTarget.dataset.text);
  },

  stopStream: function () {
    helpers.vibrate("light");
    this._stop();
    this.setData({ isStreaming: false });
  },

  _send: function (query, extraOpts) {
    var self = this;
    if (!getApp().globalData.networkAvailable) {
      wx.showToast({ title: "当前无网络连接", icon: "none", duration: 2000 });
      return;
    }
    if (self.data.isStreaming) return;
    self._stop();

    if (self._convId && !self._sid) {
      self._sid = self._convId;
      wx.setStorageSync("current_session_id", self._sid);
      wx.setStorageSync("current_session_ts", Date.now());
    }

    // 首次发消息时先创建对话，后续复用同一个 _convId
    if (!self._convId || !self._sid) {
      self.setData({ isStreaming: true });
      api
        .createConversation()
        .then(function (raw) {
          // [FIX-SESSION-ROOT-CAUSE 2026-04-01] ApiResponse 包装必须 unwrap
          // 之前直接读 data.conversation，但 data 是 {code,data,message} 包装
          // 导致 conv.id=undefined → session_id=None → 每次新 thread → 上下文断裂
          var unwrapped = api.unwrapResponse(raw);
          var conv = unwrapped.conversation || unwrapped;
          if (!conv || !conv.id) {
            log.error("Chat", "createConversation returned no id", unwrapped);
            self.setData({ isStreaming: false });
            wx.showToast({ title: "创建对话异常", icon: "none" });
            return;
          }
          self._convId = conv.id;
          self._sid = conv.id; // conversation_id 同时用作 session_id
          // [FIX-SESSION-2] 立即持久化（含时间戳），防止刷新/重启后丢失
          wx.setStorageSync("current_session_id", conv.id);
          wx.setStorageSync("current_session_ts", Date.now());
          self._doSend(query, extraOpts);
        })
        .catch(function () {
          self.setData({ isStreaming: false });
          wx.showToast({ title: "创建对话失败", icon: "none" });
        });
      return;
    }
    self._doSend(query, extraOpts);
  },

  _doSend: function (query, extraOpts) {
    var self = this;
    var autoWebSearch = !self.data.enableWebSearch && self._shouldAutoEnableWebSearch(query);
    var selectedTools = self._getSelectedTools(query);

    if (!self._sid && self._convId) {
      self._sid = self._convId;
    }
    if (!self._sid) {
      log.error("Chat", "missing session id before stream", {
        convId: self._convId || "",
      });
      wx.showToast({ title: "会话初始化失败", icon: "none" });
      return;
    }

    // 每次发消息刷新时间戳，保持活跃对话不过期
    wx.setStorageSync("current_session_ts", Date.now());

    var userMsg = { id: "u" + self._counter++, role: "user", content: query };
    var aiMsg = {
      id: "a" + self._counter++,
      role: "ai",
      content: "",
      streaming: true,
      blocks: [],
      mcqCards: null,
      mcqSelected: null,
      mcqHint: "",
      mcqReceipt: "",
      mcqInteractiveReady: false,
      thinkingStatus: "AI 正在准备...",
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
      workflowToggleText: "展开后台过程",
      workflowTone: "analyze",
      workflowActive: true,
      citations: null,
      engine: "deeptutor",
      engineSessionId: "",
      engineTurnId: "",
      billing: null,
      feedback: "",
    };
    self._streamId = aiMsg.id;
    self._buf = "";
    self._flushCount = 0;
    self._autoScrollEnabled = true;

    var existing = self.data.messages;
    var inferTitleOnStart = existing.length === 0;
    if (existing.length > MAX_MESSAGES - 2) {
      existing = existing.slice(existing.length - (MAX_MESSAGES - 2));
    }
    var msgs = existing.concat([userMsg, aiMsg]);

    self.setData({
      messages: msgs,
      hasMessages: true,
      isStreaming: true,
      scrollToId: "msg-bottom",
      chatScrollWithAnimation: false,
    });
    if (autoWebSearch) {
      wx.showToast({
        title: "检测到时效性问题，已自动联网",
        icon: "none",
        duration: 1800,
      });
    }
    // 建立 IntersectionObserver 懒解析（延迟一帧确保 DOM 已渲染）
    var setupSelf = self;
    setTimeout(function () {
      setupSelf._setupObserver();
    }, 50);
    // 对话展开后隐藏 tab bar，腾出底部空间
    if (typeof self.getTabBar === "function" && self.getTabBar()) {
      self.getTabBar().setData({ hidden: true });
    }

    // [Client Turn Idempotency] Generate stable turn ID for this message.
    // 同一轮消息在网络重连时复用同一个客户端侧标识。
    var _turnId =
      self._sid +
      "_" +
      Date.now().toString(36) +
      "_" +
      Math.random().toString(36).substr(2, 4);

    var tutorInteraction = self._buildTutorInteraction();
    self._abort = wsStream.streamChat(
      {
        query: query,
        sessionId: self._sid,
        userId: auth.getUserId(),
        mode: self.data.answerMode,
        tools: selectedTools,
        interactionProfile: tutorInteraction.profile,
        interactionHints: tutorInteraction.hints,
        clientTurnId: _turnId,
        structuredSubmitContext: extraOpts && extraOpts.structuredSubmitContext,
        followupQuestionContext: extraOpts && extraOpts.followupQuestionContext,
        inferTitleOnStart: inferTitleOnStart,
      },
      {
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
        onMcqInteractive: function (d) {
          self._onMcqInteractive(d);
        },
        onUpdatedTitle: function (title) {
          // [FIX 2026-04-01] 服务端流式推送会话标题 → 同步更新 history 缓存
          if (!title) return;
          try {
            var cacheKey = "history_cache";
            var cached = wx.getStorageSync(cacheKey);
            if (cached && cached.groups) {
              var found = false;
              cached.groups.forEach(function (g) {
                g.items.forEach(function (c) {
                  if (c.id === self._convId) {
                    c.title = title;
                    found = true;
                  }
                });
              });
              if (found) wx.setStorageSync(cacheKey, cached);
            }
          } catch (_) {}
        },
        onResult: function () {},
        onWorkflowStep: function () {},
        onWorkflowStepDone: function () {},
      },
    );
  },

  _restoreConversation: function (convId) {
    var self = this;
    self._convId = convId;
    self._sid = convId;
    // [FIX-SESSION-3] 恢复历史对话时同步持久化（含时间戳）
    wx.setStorageSync("current_session_id", convId);
    wx.setStorageSync("current_session_ts", Date.now());
    api
      .getConversationMessages(convId)
      .then(function (raw) {
        var data = api.unwrapResponse(raw);
        var rawMsgs = data.messages || data || [];
        var counter = 0;
        var msgs = rawMsgs.map(function (m) {
          var role = m.role === "assistant" ? "ai" : m.role;
          var msg = {
            id: role.charAt(0) + counter++,
            role: role,
            content: m.content || "",
            streaming: false,
            blocks: [],
            mcqCards: null,
            mcqSelected: null,
            mcqHint: "",
            mcqReceipt: "",
            mcqInteractiveReady: false,
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
            workflowToggleText: "查看完整后台过程",
            workflowTone: "compose",
            workflowActive: false,
            citations: null,
            engine: "",
            engineSessionId: "",
            engineTurnId: "",
            billing: null,
            feedback: "",
          };
          // 懒解析: 不在恢复时解析全部消息的 blocks
          // 仅解析最后几条可见消息，其余由 IntersectionObserver 按需解析
          if (role === "ai" && m.content) {
            var detected = mcqDetect.detect(m.content);
            var restoredInteractive =
              m.interactive && typeof m.interactive === "object"
                ? self._buildInteractiveMcqState(m.interactive)
                : null;
            var renderText =
              detected && detected.displayText !== undefined
                ? detected.displayText
                : m.content;
            if (counter >= rawMsgs.length - 4) {
              msg.blocks = md.parseWithIds(renderText || "");
            }
            if (restoredInteractive) {
              msg.mcqCards = restoredInteractive.cards;
              msg.mcqHint = restoredInteractive.hint;
              msg.mcqReceipt = restoredInteractive.receipt;
              msg.mcqInteractiveReady = restoredInteractive.interactiveReady;
            } else if (detected) {
              var fallbackState = self._buildFallbackMcqState(detected);
              if (fallbackState) {
                msg.mcqCards = fallbackState.cards;
                msg.mcqHint = fallbackState.hint;
                msg.mcqReceipt = fallbackState.receipt;
                msg.mcqInteractiveReady = fallbackState.interactiveReady;
              }
            }
          }
          return msg;
        });
        self._counter = counter;
        self.setData({
          messages: msgs,
          hasMessages: msgs.length > 0,
          scrollToId: "msg-bottom",
          chatScrollWithAnimation: false,
        });
        setTimeout(function () {
          self._releaseBottomAnchor();
        }, 80);
        // 建立 IntersectionObserver
        setTimeout(function () {
          self._setupObserver();
        }, 50);
      })
      .catch(function () {
        wx.showToast({ title: "加载对话失败", icon: "none" });
      });
  },

  _checkDiagnostic: function () {
    // 已做过或已跳过则不弹
    if (wx.getStorageSync("diagnostic_completed")) return;
    if (wx.getStorageSync("diagnostic_skipped")) return;
    // 只在 Hero 主页弹出
    if (this.data.hasMessages) return;

    wx.showModal({
      title: "欢迎新同学",
      content:
        "建议先做一次摸底测试（约 8 分钟），AI 会根据你的水平定制学习内容。",
      confirmText: "开始测试",
      cancelText: "稍后再说",
      success: function (res) {
        if (res.confirm) {
          wx.navigateTo({ url: "/pages/assessment/assessment" });
        } else {
          wx.setStorageSync("diagnostic_skipped", true);
        }
      },
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
      scrollToId: "",
      chatScrollWithAnimation: false,
    });
    this._sid = "s_" + Date.now();
    this._convId = null;
    this._streamId = null;
    // [FIX-SESSION-4] 用户主动清除对话时清除持久化
    wx.removeStorageSync("current_session_id");
    wx.removeStorageSync("current_session_ts");
    // 回到 Hero 首页时恢复 tab bar
    if (typeof this.getTabBar === "function" && this.getTabBar()) {
      this.getTabBar().setData({ hidden: false });
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
    if (payload.error === "missing_context") {
      wx.showToast({
        title: "题目上下文缺失，请让 AI 重新出题后再作答",
        icon: "none",
      });
      return;
    }
    helpers.vibrate("medium");
    if (msg.mcqReceipt && payload.structuredSubmitContext) {
      var questions = payload.structuredSubmitContext.questions || [];
      for (var i = 0; i < questions.length; i++) {
        questions[i].receipt = msg.mcqReceipt;
      }
    }
    this._send(payload.text, payload);
  },

  goHome: function () {
    // chat 页本身就是主页，点 logo 回到 Hero 状态
    this.clearMessages();
  },

  goProfile: function () {
    wx.navigateTo({ url: "/pages/profile/profile" });
  },

  goRecharge: function () {
    wx.navigateTo({ url: "/pages/billing/billing" });
  },

  onToggleTheme: function () {
    helpers.vibrate("light");
    var dark = !this.data.isDark;
    var themeVal = dark ? "dark" : "light";
    helpers.setTheme(themeVal); // 统一写入 globalData + Storage
    this.setData({ isDark: dark });
    helpers.syncTabBar(this, 0, { hidden: this.data.hasMessages });
    wx.showToast({
      title: dark ? "深色模式" : "浅色模式",
      icon: "none",
      duration: 1000,
    });
  },

  goBilling: function () {
    var self = this;
    self.setData({ billingShow: true, billingLoading: true });
    // 并行加载余额和流水
    var reasonMap = {
      capture: "对话消耗",
      grant: "每日赠送",
      refund: "退回",
      purchase: "充值",
      admin_grant: "系统赠送",
      signup_bonus: "注册奖励",
    };
    api
      .getWallet()
      .then(function (data) {
        var d = api.unwrapResponse(data);
        self.setData({ billingBalance: d.balance || 0 });
      })
      .catch(function (err) {
        log.warn("Chat", "getWallet failed: " + ((err && err.message) || err));
      });
    api
      .getLedger(30)
      .then(function (raw) {
        var data = api.unwrapResponse(raw);
        var entries = (data.entries || []).map(function (e) {
          var d = new Date(e.created_at || "");
          var time = isNaN(d)
            ? ""
            : d.getMonth() +
              1 +
              "/" +
              d.getDate() +
              " " +
              (d.getHours() < 10 ? "0" : "") +
              d.getHours() +
              ":" +
              (d.getMinutes() < 10 ? "0" : "") +
              d.getMinutes();
          return {
            id: e.id,
            delta: e.delta,
            reason: reasonMap[e.reason] || e.reason || "智力点变动",
            time: time,
            isDebit: e.delta < 0,
          };
        });
        self.setData({ billingEntries: entries, billingLoading: false });
      })
      .catch(function (err) {
        log.warn("Chat", "getLedger failed: " + ((err && err.message) || err));
        self.setData({ billingLoading: false });
      });
  },

  closeBilling: function () {
    this.setData({ billingShow: false });
  },

  onCopy: function (e) {
    helpers.vibrate("light");
    var msg = this.data.messages.find(function (m) {
      return m.id === e.currentTarget.dataset.msgid;
    });
    if (msg) wx.setClipboardData({ data: msg.content });
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

  onEdit: function (e) {
    helpers.vibrate("light");
    var msg = this.data.messages.find(function (m) {
      return m.id === e.currentTarget.dataset.msgid;
    });
    if (msg) {
      this._inputText = msg.content;
      this.setData({ inputText: msg.content });
    }
  },

  onRetry: function (e) {
    if (this.data.isStreaming) return;
    helpers.vibrate("medium");
    var msgid = e.currentTarget.dataset.msgid;
    var msgs = this.data.messages;
    var aiIdx = -1;
    for (var i = 0; i < msgs.length; i++) {
      if (msgs[i].id === msgid) {
        aiIdx = i;
        break;
      }
    }
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
    this.setData({ messages: newMsgs });
    this._send(userMsg.content);
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
    });
  },

  onFeedbackTag: function (e) {
    var tag = e.currentTarget.dataset.tag;
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
    this.setData({ feedbackComment: e.detail.value });
  },

  onFeedbackSubmit: function () {
    var msgid = this.data.feedbackMsgId;
    if (!msgid) return;
    this._sendFeedback(
      msgid,
      -1,
      this.data.feedbackTags,
      this.data.feedbackComment,
    );
    wx.showToast({ title: "感谢反馈", icon: "success", duration: 1500 });
    this.setData({ feedbackMsgId: "", feedbackTags: [], feedbackComment: "" });
  },

  onFeedbackClose: function () {
    this.setData({ feedbackMsgId: "", feedbackTags: [], feedbackComment: "" });
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
    api.submitFeedback({
      message_id: msgid,
      conversation_id: this._convId || "",
      rating: rating,
      reason_tags: tags || [],
      comment: comment || "",
      answer_mode: this.data.answerMode || "AUTO",
    });
  },
});
