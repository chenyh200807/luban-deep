// test_package_chat_10d_paper_repave_contract.js — 10d 问鲁班纸墨朱竹重铺视觉/文案契约
// Run: node yousenwebview/tests/test_package_chat_10d_paper_repave_contract.js
//
// 覆盖：10d 顶栏归位（会话历史时钟二级页 + 新对话）、上下文带入条、快捷入口、
// 导回钩子重铺、纸墨朱竹 token 单一权威、流式等待文案、教学卡深链承接、
// 文案禁审视词（看穿/识破/揭穿/露馅/拆穿）、WXML 标签平衡。

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function read(rel) {
  return fs.readFileSync(path.join(__dirname, "../packageDeeptutor", rel), "utf8");
}

var chatWxml = read("pages/chat/chat.wxml");
var chatWxss = read("pages/chat/chat.wxss");
var chatJs = read("pages/chat/chat.js");
var historyWxml = read("pages/history/history.wxml");
var historyJs = read("pages/history/history.js");

/* ── 1. WXML 标签平衡（自闭合感知） ─────────────────────── */
function checkWxmlBalance(source) {
  var src = source.replace(/<!--[\s\S]*?-->/g, "").replace(/<wxs[\s\S]*?<\/wxs>/g, "");
  var re = /<(\/?)([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^><"'])*)>/g;
  var stack = [];
  var match;
  while ((match = re.exec(src))) {
    var closing = match[1] === "/";
    var name = match[2];
    var attrs = match[3] || "";
    if (attrs.replace(/\s+$/, "").slice(-1) === "/") continue; // 自闭合
    if (closing) {
      if (!stack.length || stack[stack.length - 1] !== name) {
        return "mismatched </" + name + "> (stack top: " + stack.slice(-3).join(",") + ")";
      }
      stack.pop();
    } else {
      stack.push(name);
    }
  }
  return stack.length ? "unclosed: " + stack.join(",") : "";
}
assert(checkWxmlBalance(chatWxml) === "", "chat.wxml tags must balance: " + checkWxmlBalance(chatWxml));
assert(checkWxmlBalance(historyWxml) === "", "history.wxml tags must balance");

/* ── 2. 文案禁审视词（wow=看穿但必须暖 → 端上文案一律禁审视语气） ── */
var forbidden = ["看穿", "识破", "揭穿", "露馅", "拆穿"];
[
  ["chat.wxml", chatWxml],
  ["chat.js", chatJs],
  ["chat.wxss", chatWxss],
  ["history.wxml", historyWxml],
  ["history.js", historyJs],
].forEach(function (pair) {
  forbidden.forEach(function (word) {
    assert(pair[1].indexOf(word) < 0, pair[0] + " must not contain audit-tone word " + word);
  });
});

/* ── 3. 10d 顶栏：标题 + 会话历史时钟二级页 + 新对话 ───────── */
assert(chatWxml.indexOf('<text class="nav-title">问鲁班</text>') >= 0, "navbar shows 问鲁班 title");
assert(chatWxml.indexOf("续着上次聊 · 问完就练") >= 0, "navbar shows resume subtitle");
assert(
  /class="nav-icon-btn nav-history-chat" bindtap="goHistoryPage"/.test(chatWxml) &&
    chatWxml.indexOf('aria-label="会话历史"') >= 0,
  "history clock entry must bind goHistoryPage in navbar",
);
var historyHandler = (chatJs.match(/goHistoryPage:\s*function[\s\S]*?\n  \},/) || [""])[0];
assert(
  historyHandler.indexOf("route.history()") >= 0 &&
    historyHandler.indexOf('isFeatureEnabled("history")') >= 0,
  "goHistoryPage must reuse pages/history via route.history() behind the history flag",
);
assert(
  chatWxml.indexOf('bindtap="clearMessages" aria-role="button" aria-label="新建对话"') >= 0,
  "new-chat button preserved in navbar",
);

/* ── 4. 上下文带入条：可见化既有载体，无上下文不渲染 ───────── */
assert(
  (chatWxml.match(/class="ctx-chip-row" wx:if="\{\{contextBanner\}\}"/g) || []).length >= 2,
  "context banner renders in both hero and chat states, gated on contextBanner",
);
assert(
  chatJs.indexOf("buildContextBannerLabel(") >= 0 &&
    chatJs.indexOf("sendOptions.followupQuestionContext") >= 0,
  "context banner must derive from the existing followupContext/promptIntent carriers",
);

/* ── 5. 快捷入口：只做出几道题 + 看动画讲解；拍照批改后置不做 ── */
assert(
  chatWxml.indexOf("出几道题") >= 0 && chatWxml.indexOf("看动画讲解") >= 0,
  "quick entries 出几道题 / 看动画讲解 present",
);
var chatWxmlNoComments = chatWxml.replace(/<!--[\s\S]*?-->/g, "");
assert(
  chatWxmlNoComments.indexOf("拍照批改") < 0,
  "拍照批改 deferred by owner — must not render (comments documenting the deferral are fine)",
);
var composeHandler = (chatJs.match(/onQuickComposeQuestions:\s*function[\s\S]*?\n  \},/) || [""])[0];
assert(
  composeHandler.indexOf("setData({ inputText") >= 0 && composeHandler.indexOf("_send(") < 0,
  "出几道题 must only prefill intent, never auto-send",
);
var animHandler = (chatJs.match(/onQuickAnimLesson:\s*function[\s\S]*?\n  \},/) || [""])[0];
assert(
  animHandler.indexOf("route.lubanStations()") >= 0,
  "看动画讲解 must deep-link the existing stations page (no new backend)",
);

/* ── 6. 导回钩子：nba 单 CTA 重铺，未投影的两选项不做不造 ──── */
assert(
  chatWxml.indexOf("懂了不等于会写——现在练一下？") >= 0 &&
    chatWxml.indexOf("练一道同类题") >= 0,
  "10d flow-back hook copy on next_best_action card",
);
assert(
  chatWxml.indexOf("加入今日任务") < 0 || /TODO/.test(chatWxml),
  "unprojected options (加入今日任务/我会了) must not render as live UI",
);
assert(
  /TODO\(10d 导回三选一\)/.test(chatWxml),
  "wxml must keep the TODO marker for the two unprojected flow-back options",
);

/* ── 7. 纸墨朱竹 token 单一权威 ───────────────────────────── */
assert(
  chatWxss.indexOf('@import "/packageDeeptutor/styles/paper-ink.wxss"') >= 0,
  "chat.wxss must import the shared paper-ink token sheet",
);
assert(
  /class="page paper pk-paper-bg \{\{isDark\?'':'light'\}\}"/.test(chatWxml),
  "page root must mount paper tokens + dot-grid background",
);
assert(
  !/--pk-(paper|card|bd|t1|t2|t3|red|grn|warn|ink-btn|gauge|dot|shadow)\s*:/.test(chatWxss),
  "chat.wxss must not redefine --pk-* tokens (paper-ink.wxss is the single authority)",
);
assert(
  chatWxml.indexOf("aurora-layer") < 0 && chatWxml.indexOf("bg_horizon") < 0,
  "old aurora/horizon背景 must be replaced by宣纸底",
);

/* ── 8. 流式等待文案 ─────────────────────────────────────── */
assert(
  chatJs.indexOf("鲁班正在按采分点琢磨…") >= 0,
  "streaming wait copy must be 鲁班正在按采分点琢磨…",
);
assert(
  chatJs.indexOf("AI 正在分析你的问题") < 0,
  "old generic wait copy must be gone from chat.js",
);

/* ── 9. 教学卡「问追AI」深链承接 ─────────────────────────── */
assert(
  chatJs.indexOf('"teach_card"') >= 0 &&
    chatJs.indexOf("options.pack_id") >= 0 &&
    chatJs.indexOf("options.scene_title") >= 0,
  "onLoad must accept teach_card deep-link params via the existing entrySource system",
);
assert(
  chatJs.indexOf("针对这一站提问…") >= 0,
  "teach_card entry must preset the station-question placeholder",
);
assert(
  chatJs.indexOf("_teachEntryIntent && !sendOptions.promptIntent") >= 0,
  "teach context must merge into the existing promptIntent carrier on first send (no new channel)",
);
assert(
  chatJs.indexOf("getLubanLessonDetail") >= 0,
  "pack title should resolve from the existing lessons API with param fallback",
);
assert(
  /placeholder="\{\{inputPlaceholder\}\}"/.test(chatWxml),
  "hero textarea placeholder must bind inputPlaceholder",
);

/* ── 10. 带入条派生逻辑（vm 加载页面配置直接调用） ─────────── */
function loadChatPage() {
  var source = read("pages/chat/chat.js");
  var pageDef = null;
  var helpersMock = {
    getAnimConfig: function () {
      return {
        flushThrottleMs: 16,
        mdParseInterval: 3,
        enableBreathingOrbs: false,
        enableMarquee: false,
        enableMsgAnimation: false,
        enableFocusPulse: false,
      };
    },
    getWindowInfo: function () {
      return {
        statusBarHeight: 20,
        windowWidth: 375,
        screenWidth: 375,
        windowHeight: 812,
        screenHeight: 812,
        safeArea: { bottom: 778 },
      };
    },
    isDark: function () {
      return true;
    },
    getTimeGreeting: function () {
      return "上午好";
    },
    syncTabBar: function () {},
    vibrate: function () {},
  };
  var sandbox = {
    console: { warn: function () {}, error: function () {}, log: function () {} },
    Date: Date,
    Math: Math,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") return {};
      if (request === "../../utils/api") {
        return { unwrapResponse: function (raw) { return raw; } };
      }
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/helpers") return helpersMock;
      if (request === "../../utils/logger") return { warn: function () {}, error: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/surface-telemetry") {
        return { track: function () {}, trackOnce: function () {} };
      }
      if (request === "../../utils/runtime") return {};
      if (request === "../../utils/route") return {};
      if (request === "../../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () { return false; },
          isFeatureEnabled: function () { return true; },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      if (request === "../../utils/history-tombstone") {
        return { rememberDeletedConversationIds: function () {} };
      }
      if (request === "../../utils/learning-home-view-model") {
        return require(path.join(__dirname, "../packageDeeptutor/utils/learning-home-view-model.js"));
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () { return ""; },
      setStorageSync: function () {},
      removeStorageSync: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
    getApp: function () { return {}; },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "chat.js" });
  return pageDef;
}

var page = loadChatPage();
assert(!!page, "chat page config must load in vm");
if (page) {
  var label = page._buildContextBannerLabel(null, {
    source: "teach_card",
    concept_id: "C02",
    concept_label: "工期索赔",
    scene_title: "第 2 幕",
  });
  assert(label === "已带入：工期索赔 · 讲懂卡", "teach_card banner uses pack title · 讲懂卡, got: " + label);
  var fallbackLabel = page._buildContextBannerLabel(null, {
    source: "teach_card",
    concept_id: "C02",
    concept_label: "",
    scene_title: "",
  });
  assert(fallbackLabel === "已带入：C02 · 讲懂卡", "teach_card banner falls back to pack_id, got: " + fallbackLabel);
  var stemLabel = page._buildContextBannerLabel(
    { question: "某工程因业主原因导致关键线路上的工作延误 5 天，承包人应如何索赔？" },
    null,
  );
  assert(
    stemLabel.indexOf("已带入：") === 0 && stemLabel.length <= "已带入：".length + 15,
    "question banner truncates the stem, got: " + stemLabel,
  );
  var groupLabel = page._buildContextBannerLabel(
    { question_id: "question_set", question: "…", items: [{}, {}, {}] },
    null,
  );
  assert(groupLabel === "已带入：本组 3 题作答", "question-set banner counts items, got: " + groupLabel);
  var emptyLabel = page._buildContextBannerLabel(null, null);
  assert(emptyLabel === "", "no context → empty banner → chip not rendered");
  var unrelatedIntent = page._buildContextBannerLabel(null, {
    learning_signal_type: "assessment_wrong_item_practice",
  });
  assert(unrelatedIntent === "", "non teach_card promptIntent must not fabricate a banner");
}

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_package_chat_10d_paper_repave_contract.js (" + pass + " assertions)");
