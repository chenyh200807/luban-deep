// test_package_chat_copy_authority.js — packageDeeptutor copy button should use visible content
// Run: node yousenwebview/tests/test_package_chat_copy_authority.js

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

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
    pass++;
    return;
  }
  fail++;
  errors.push(
    "FAIL: " +
      message +
      "\n  expected: " +
      JSON.stringify(expected) +
      "\n  actual:   " +
      JSON.stringify(actual),
  );
}

function loadChatPage(options) {
  var opts = options || {};
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );
  var pageDef = null;
  var clipboard = [];
  var toasts = [];
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
    console: { warn: function () {}, error: console.error, log: console.log },
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
      if (request === "../../utils/surface-telemetry") return { track: function () {}, trackOnce: function () {} };
      if (request === "../../utils/runtime") return {};
      if (request === "../../utils/route") return {};
      if (request === "../../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () { return false; },
          isFeatureEnabled: function () { return true; },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      if (request === "../../utils/history-tombstone") return { rememberDeletedConversationIds: function () {} };
      if (request === "../../utils/learning-home-view-model") return require(path.join(__dirname, "../packageDeeptutor/utils/learning-home-view-model.js"));
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () {
        return "";
      },
      setStorageSync: function () {},
      removeStorageSync: function () {},
      setClipboardData: function (payload) {
        if (opts.clipboardShouldFail) {
          if (payload && typeof payload.fail === "function") {
            payload.fail({ errMsg: opts.clipboardErrorMessage || "setClipboardData:fail mocked" });
          }
          return;
        }
        clipboard.push(payload.data);
        if (payload && typeof payload.success === "function") {
          payload.success({ errMsg: "setClipboardData:ok" });
        }
      },
      showToast: function (payload) {
        toasts.push(payload);
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "yousenwebview/packageDeeptutor/pages/chat/chat.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });
  return { page: page, clipboard: clipboard, toasts: toasts };
}

var loaded = loadChatPage();
var chatSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);
var chatWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
  "utf8",
);
assert(
  chatWxml.indexOf("onSaveNotebookCard") >= 0 &&
    chatWxml.indexOf("存卡") >= 0,
  "chat AI answer actions should expose the P0A save-card entry",
);
assert(
  chatSource.indexOf("api.saveNotebookCard") >= 0 &&
    chatSource.indexOf("note_card_saved") >= 0 &&
    chatSource.indexOf("surfaceTelemetry.trackProductBehavior") >= 0,
  "chat save-card entry should use NotebookCardService routing and product_behavior authority",
);
loaded.page.setData({
  messages: [
    {
      id: "a1",
      role: "ai",
      content: "",
      renderableContent: "",
      blocks: [
        {
          type: "table",
          caption: "防火门考点",
          headers: [
            { content: [{ type: "text", text: "考点" }] },
            { nodes: [{ type: "text", text: "分值" }] },
          ],
          rows: [
            [
              { content: [{ type: "text", text: "防火门" }] },
              {
                nodes: [
                  {
                    name: "span",
                    children: [{ type: "text", text: "2" }],
                  },
                ],
              },
            ],
          ],
        },
        {
          type: "formula_block",
          displayText: "A = πr²",
          copyText: "A = \\pi r^2",
        },
      ],
      mcqCards: null,
    },
    {
      id: "a2",
      role: "ai",
      content: "raw fallback should not win",
      renderableContent: "",
      blocks: [],
      mcqCards: [
        {
          index: 1,
          stem: "防火门构造的基本要求有（ ）。",
          options: [
            { key: "A", text: "耐火极限符合要求" },
            { key: "B", text: "可以任意开启" },
          ],
        },
      ],
    },
    {
      id: "a3",
      role: "ai",
      content: "",
      renderableContent: "",
      blocks: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "后台处理已经完成，" },
            { type: "strong", children: [{ type: "text", text: "可复制可见文本" }] },
          ],
        },
        {
          type: "ul",
          items: [
            {
              nodes: [
                { type: "text", text: "不要复制 " },
                { type: "code", children: [{ type: "text", text: "[object Object]" }] },
              ],
            },
          ],
        },
      ],
      mcqCards: null,
    },
  ],
});

loaded.page.onCopy({ currentTarget: { dataset: { msgid: "a1" } } });
assert(
  loaded.clipboard[0].indexOf("防火门考点") >= 0 &&
    loaded.clipboard[0].indexOf("考点 | 分值") >= 0 &&
    loaded.clipboard[0].indexOf("A = \\pi r^2") >= 0,
  "copy should serialize visible structured blocks when raw content is empty",
);

loaded.page.onCopy({ currentTarget: { dataset: { msgid: "a2" } } });
assert(
  loaded.clipboard[1].indexOf("防火门构造的基本要求") >= 0 &&
    loaded.clipboard[1].indexOf("A. 耐火极限符合要求") >= 0 &&
    loaded.clipboard[1].indexOf("raw fallback should not win") < 0,
  "copy should prefer visible MCQ cards over raw fallback text",
);

loaded.page.onCopy({ currentTarget: { dataset: { msgid: "a3" } } });
assert(
  loaded.clipboard[2].indexOf("后台处理已经完成，可复制可见文本") >= 0 &&
    loaded.clipboard[2].indexOf("- 不要复制 [object Object]") >= 0 &&
    loaded.clipboard[2] !== "[object Object],[object Object]",
  "copy should serialize markdown rich-text node arrays instead of object placeholders",
);

loaded.page.setData({
  messages: [
    {
      id: "a4",
      role: "ai",
      content: "第一次新对话回答",
      renderableContent: "第一次新对话回答",
      blocks: [],
      mcqCards: null,
    },
  ],
});
loaded.page.onCopy({ currentTarget: { dataset: { msgid: "a4" } } });
loaded.page.setData({
  messages: [
    {
      id: "a5",
      role: "ai",
      content: "第二次新对话回答",
      renderableContent: "第二次新对话回答",
      blocks: [],
      mcqCards: null,
    },
  ],
});
loaded.page.onCopy({ currentTarget: { dataset: { msgid: "a5" } } });
assertEqual(loaded.clipboard[3], "第一次新对话回答", "first new answer copy should write its visible text");
assertEqual(loaded.clipboard[4], "第二次新对话回答", "second new answer copy should write its visible text");
assertEqual(
  loaded.toasts,
  [
    { title: "内容已复制", icon: "success", duration: 1200 },
    { title: "内容已复制", icon: "success", duration: 1200 },
    { title: "内容已复制", icon: "success", duration: 1200 },
    { title: "内容已复制", icon: "success", duration: 1200 },
    { title: "内容已复制", icon: "success", duration: 1200 },
  ],
  "successful copies should show copied feedback every time",
);

var failedLoaded = loadChatPage({ clipboardShouldFail: true });
failedLoaded.page.setData({
  messages: [
    {
      id: "a6",
      role: "ai",
      content: "这次微信剪贴板拒绝写入",
      renderableContent: "这次微信剪贴板拒绝写入",
      blocks: [],
      mcqCards: null,
    },
  ],
});
failedLoaded.page.onCopy({ currentTarget: { dataset: { msgid: "a6" } } });
assertEqual(failedLoaded.clipboard.length, 0, "failed clipboard writes should not be recorded");
assertEqual(
  failedLoaded.toasts[0],
  { title: "复制失败，请重试", icon: "none", duration: 1800 },
  "failed copy button writes should not redirect users to long-press selection",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_chat_copy_authority.js (" + pass + " assertions)");
